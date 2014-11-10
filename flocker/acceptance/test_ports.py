# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for communication to applications across nodes.
"""
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

from flocker.node._docker import BASE_NAMESPACE, PortMap, Unit, Volume

from .testtools import (assert_expected_deployment, flocker_deploy,
                        get_mongo_client, get_nodes, MONGO_APPLICATION,
                        MONGO_IMAGE, require_flocker_cli, require_mongo)


class PortsTests(TestCase):
    """
    Tests for communication to applications across nodes.

    Similar to:
    http://doc-dev.clusterhq.com/gettingstarted/tutorial/exposing-ports.html
    """
    @require_flocker_cli
    def setUp(self):
        """
        Deploy an application with an internal port mapped to a different
        external port.
        """
        getting_nodes = get_nodes(num_nodes=2)

        def deploy_port_application(node_ips):
            self.node_1, self.node_2 = node_ips

            self.internal_port = 27017
            self.external_port = 27018

            port_deployment = {
                u"version": 1,
                u"nodes": {
                    self.node_1: [MONGO_APPLICATION],
                    self.node_2: [],
                },
            }

            port_application = {
                u"version": 1,
                u"applications": {
                    MONGO_APPLICATION: {
                        u"image": MONGO_IMAGE,
                        u"ports": [{
                            u"internal": self.internal_port,
                            u"external": self.external_port,
                        }],
                    },
                },
            }

            flocker_deploy(self, port_deployment, port_application)

        getting_nodes.addCallback(deploy_port_application)
        return getting_nodes

    def test_deployment_with_ports(self):
        """
        Ports are exposed as specified in the application configuration.
        Docker has internal representations of the port mappings given by the
        configuration files supplied to flocker-deploy.
        """
        unit = Unit(name=MONGO_APPLICATION,
                    container_name=BASE_NAMESPACE + MONGO_APPLICATION,
                    activation_state=u'active',
                    container_image=MONGO_IMAGE + u':latest',
                    ports=frozenset([
                        PortMap(internal_port=self.internal_port,
                                external_port=self.external_port)
                    ]),
                    volumes=frozenset([
                        # TODO MONGO_VOLUMES in testtools
                        Volume(node_path=FilePath(b'/some_path'),
                               container_path=FilePath(b'/data/db')),
                        Volume(node_path=FilePath(b'/some_path'),
                               container_path=FilePath(b'/data/log')),
                    ]))

        d = assert_expected_deployment(self, {
            self.node_1: set([unit]),
            self.node_2: set([]),
        })

        return d

    @require_mongo
    def test_traffic_routed(self):
        """
        An application can be accessed even from a connection to a node
        which it is not running on. In particular, if MongoDB is deployed to a
        node, and data added to it, that data is visible when a client connects
        to a different node on the cluster.
        """
        getting_client = get_mongo_client(self.node_1, self.external_port)

        def verify_traffic_routed(client_1):
            posts_1 = client_1.example.posts
            posts_1.insert({u"the data": u"it moves"})

            d = get_mongo_client(self.node_2, self.external_port)
            d.addCallback(lambda client_2: self.assertEqual(
                posts_1.find_one(),
                client_2.example.posts.find_one()
            ))

            return d

        getting_client.addCallback(verify_traffic_routed)
        return getting_client
