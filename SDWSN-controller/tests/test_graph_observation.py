import unittest

import numpy as np

from sdwsn_controller.node.node import Node
from sdwsn_controller.reinforcement_learning.graph_observation import (
    EDGE_FEATURE_NAMES,
    GLOBAL_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    GraphObservation,
    GraphObservationBuilder,
)
from sdwsn_controller.tsch.schedule import cell_type


class FakeNetwork:
    def __init__(self):
        self.nodes = {}
        self.tsch_slotframe_size = 35

    def tsch_last_ts(self):
        return max((node.tsch_last_ts() for node in self.nodes.values()), default=0)


class GraphObservationBuilderTest(unittest.TestCase):
    def setUp(self):
        self.network = FakeNetwork()
        controller = Node(0, sid="1.1", rank=0)
        sink = Node(1, sid=None, rank=0)
        node_2 = Node(2, sid=None, rank=1)
        node_3 = Node(3, sid=None, rank=255)
        self.network.nodes = {
            3: node_3,
            0: controller,
            2: node_2,
            1: sink,
        }

        node_2.neighbor_add(1, rssi=-60, etx=128)
        node_2.neighbor_add(99, rssi=-70, etx=128)
        node_3.neighbor_add(2, rssi=-80, etx=256)
        node_2.energy_add(seq=1, energy=2500)
        node_2.delay_add(seq=1, delay=7505)
        node_2.pdr_add(seq=1)
        node_2.pdr_add(seq=2)
        node_2.route_add(dst_id=0, nexthop_id=1)
        node_2.tsch_add_link(
            schedule_type=cell_type.UC_TX,
            ch=0,
            ts=7,
            dst=1,
        )
        sink.tsch_add_link(
            schedule_type=cell_type.UC_RX,
            ch=0,
            ts=7,
            dst=2,
        )

        self.builder = GraphObservationBuilder(max_slotframe_size=70)

    def test_builds_deterministic_graph_and_excludes_virtual_controller(self):
        observation = self.builder.build(
            self.network,
            user_requirements=(0.4, 0.3, 0.3),
        )

        np.testing.assert_array_equal(observation.node_ids, [1, 2, 3])
        self.assertEqual(
            observation.node_features.shape,
            (3, len(NODE_FEATURE_NAMES)),
        )
        np.testing.assert_array_equal(
            observation.edge_index,
            np.asarray([[1, 2], [0, 1]], dtype=np.int64),
        )
        self.assertEqual(
            observation.edge_features.shape,
            (2, len(EDGE_FEATURE_NAMES)),
        )
        self.assertEqual(
            observation.global_features.shape,
            (len(GLOBAL_FEATURE_NAMES),),
        )
        self.assertEqual(observation.node_features.dtype, np.float32)
        self.assertEqual(observation.edge_features.dtype, np.float32)
        self.assertEqual(observation.global_features.dtype, np.float32)
        self.assertTrue(np.isfinite(observation.node_features).all())
        self.assertTrue(np.isfinite(observation.edge_features).all())
        self.assertTrue(np.isfinite(observation.global_features).all())

    def test_normalizes_metrics_and_marks_missing_values(self):
        observation = self.builder.build(
            self.network,
            user_requirements=(0.4, 0.3, 0.3),
        )
        features = {
            node_id: dict(zip(NODE_FEATURE_NAMES, values))
            for node_id, values in zip(
                observation.node_ids,
                observation.node_features,
            )
        }

        self.assertEqual(features[1]["is_sink"], 1.0)
        self.assertAlmostEqual(features[2]["rank_normalized"], 1.0 / 254.0)
        self.assertEqual(features[2]["rank_available"], 1.0)
        self.assertAlmostEqual(features[2]["neighbor_degree_normalized"], 0.5)
        self.assertAlmostEqual(features[2]["energy_normalized"], 0.5)
        self.assertAlmostEqual(features[2]["delay_normalized"], 0.5)
        self.assertEqual(features[2]["pdr"], 1.0)
        self.assertEqual(features[2]["energy_available"], 1.0)
        self.assertEqual(features[2]["delay_available"], 1.0)
        self.assertEqual(features[2]["pdr_available"], 1.0)
        self.assertAlmostEqual(
            features[2]["tx_cell_count_normalized"],
            1.0 / 70.0,
        )

        self.assertEqual(features[3]["rank_normalized"], 0.0)
        self.assertEqual(features[3]["rank_available"], 0.0)
        self.assertEqual(features[3]["energy_normalized"], 0.0)
        self.assertEqual(features[3]["energy_available"], 0.0)
        self.assertEqual(features[3]["delay_available"], 0.0)
        self.assertEqual(features[3]["pdr_available"], 0.0)

    def test_encodes_link_quality_route_and_schedule(self):
        observation = self.builder.build(
            self.network,
            user_requirements=(0.4, 0.3, 0.3),
        )
        edges = [
            dict(zip(EDGE_FEATURE_NAMES, values))
            for values in observation.edge_features
        ]

        self.assertAlmostEqual(edges[0]["rssi_strength"], 0.4)
        self.assertEqual(edges[0]["rssi_available"], 1.0)
        self.assertEqual(edges[0]["etx_quality"], 1.0)
        self.assertEqual(edges[0]["etx_available"], 1.0)
        self.assertEqual(edges[0]["selected_route"], 1.0)
        self.assertEqual(edges[0]["tsch_scheduled"], 1.0)

        self.assertAlmostEqual(edges[1]["rssi_strength"], 0.2)
        self.assertAlmostEqual(edges[1]["etx_quality"], 0.5)
        self.assertEqual(edges[1]["selected_route"], 0.0)
        self.assertEqual(edges[1]["tsch_scheduled"], 0.0)

    def test_encodes_global_requirements_and_slotframe_state(self):
        observation = self.builder.build(
            self.network,
            user_requirements=(0.4, 0.3, 0.3),
        )
        global_features = dict(
            zip(GLOBAL_FEATURE_NAMES, observation.global_features)
        )

        self.assertAlmostEqual(global_features["alpha"], 0.4)
        self.assertAlmostEqual(global_features["beta"], 0.3)
        self.assertAlmostEqual(global_features["delta"], 0.3)
        self.assertAlmostEqual(
            global_features["slotframe_size_normalized"],
            0.5,
        )
        self.assertAlmostEqual(
            global_features["last_active_timeslot_normalized"],
            0.1,
        )

    def test_rejects_network_without_observable_nodes(self):
        self.network.nodes = {0: self.network.nodes[0]}

        with self.assertRaisesRegex(ValueError, "observable nodes"):
            self.builder.build(
                self.network,
                user_requirements=(0.4, 0.3, 0.3),
            )

    def test_preserves_shapes_when_edges_or_link_measurements_are_missing(self):
        self.network.nodes[2].neighbors.clear()
        self.network.nodes[3].neighbors.clear()
        observation = self.builder.build(
            self.network,
            user_requirements=(0.4, 0.3, 0.3),
        )

        self.assertEqual(observation.edge_index.shape, (2, 0))
        self.assertEqual(
            observation.edge_features.shape,
            (0, len(EDGE_FEATURE_NAMES)),
        )

        self.network.nodes[2].neighbor_add(1, rssi=0, etx=0)
        observation = self.builder.build(
            self.network,
            user_requirements=(0.4, 0.3, 0.3),
        )
        edge = dict(zip(EDGE_FEATURE_NAMES, observation.edge_features[0]))

        self.assertEqual(edge["rssi_strength"], 0.0)
        self.assertEqual(edge["rssi_available"], 0.0)
        self.assertEqual(edge["etx_quality"], 0.0)
        self.assertEqual(edge["etx_available"], 0.0)
        self.assertTrue(np.isfinite(observation.edge_features).all())

    def test_graph_observation_rejects_non_finite_features(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            GraphObservation(
                node_ids=np.asarray([1], dtype=np.int64),
                node_features=np.full(
                    (1, len(NODE_FEATURE_NAMES)),
                    np.nan,
                    dtype=np.float32,
                ),
                edge_index=np.empty((2, 0), dtype=np.int64),
                edge_features=np.empty(
                    (0, len(EDGE_FEATURE_NAMES)),
                    dtype=np.float32,
                ),
                global_features=np.zeros(
                    len(GLOBAL_FEATURE_NAMES),
                    dtype=np.float32,
                ),
            )


if __name__ == "__main__":
    unittest.main()
