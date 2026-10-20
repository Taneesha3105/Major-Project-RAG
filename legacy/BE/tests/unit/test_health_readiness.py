import unittest

from app.core.readiness import readiness_state


class HealthReadinessTests(unittest.TestCase):
    def tearDown(self) -> None:
        readiness_state.reset()

    def test_snapshot_is_ready_when_database_and_embedding_are_ready(self):
        readiness_state.begin_startup(requires_local_embedding=True, embedding_runtime="sentence_transformers")
        readiness_state.mark_database_ready()
        readiness_state.mark_embedding_ready(runtime="sentence_transformers")

        snapshot = readiness_state.snapshot()

        self.assertEqual(snapshot.status, "ready")
        self.assertTrue(snapshot.database_ready)
        self.assertTrue(snapshot.embedding_ready)
        self.assertEqual(snapshot.embedding_state, "ready")

    def test_snapshot_stays_starting_while_embedding_is_warming(self):
        readiness_state.begin_startup(requires_local_embedding=True, embedding_runtime="sentence_transformers")
        readiness_state.mark_database_ready()
        readiness_state.mark_embedding_warming(runtime="sentence_transformers")

        snapshot = readiness_state.snapshot()

        self.assertEqual(snapshot.status, "starting")
        self.assertTrue(snapshot.database_ready)
        self.assertFalse(snapshot.embedding_ready)
        self.assertEqual(snapshot.embedding_state, "warming")


if __name__ == "__main__":
    unittest.main()
