import unittest

from av_editor.models import SourceState, TimelineEvent, VideoSource
from av_editor.timeline import build_state_segments, parse_includes, build_chunks


class TestTimeline(unittest.TestCase):
    def test_parse_includes_empty(self):
        inc = parse_includes({}, production_start=10.0, production_end=20.0)
        self.assertEqual(len(inc), 1)
        self.assertAlmostEqual(inc[0].start, 10.0)
        self.assertAlmostEqual(inc[0].end, 20.0)

    def test_parse_includes_merge_and_clip(self):
        includes = {
            'a': [0.0, 5.0],
            'b': [[4.0, 8.0]],
            'c': [30.0, 40.0],
        }
        inc = parse_includes(includes, production_start=2.0, production_end=10.0)
        # [0,5] and [4,8] clip to [2,5] and [4,8] merge to [2,8]
        self.assertEqual(len(inc), 1)
        self.assertAlmostEqual(inc[0].start, 2.0)
        self.assertAlmostEqual(inc[0].end, 8.0)

    def test_state_segments_persistence(self):
        # One source with partial updates
        src = VideoSource(
            name='cam',
            file='dummy.mp4',
            clap_time=0.0,
            default_state=SourceState(
                z_index=0,
                position_x_pct=0,
                position_y_pct=0,
                scale_pct=100,
                crop_left_pct=0,
                crop_right_pct=0,
                crop_top_pct=0,
                crop_bottom_pct=0,
            ),
            timeline=[
                TimelineEvent(at=2.0, position=(10.0, 20.0)),
                TimelineEvent(at=4.0, scale_pct=50.0),
                TimelineEvent(at=6.0, z_index=3.0),
            ],
        )

        segs = build_state_segments([src], production_start=0.0, production_end=10.0)
        self.assertEqual(len(segs), 4)

        # 0-2 default
        self.assertEqual(segs[0].start, 0.0)
        self.assertEqual(segs[0].end, 2.0)
        st0 = segs[0].state_by_source['cam']
        self.assertEqual(st0.z_index, 0)
        self.assertEqual(st0.position_x_pct, 0)
        self.assertEqual(st0.scale_pct, 100)

        # 2-4 position updated
        st1 = segs[1].state_by_source['cam']
        self.assertEqual(st1.position_x_pct, 10.0)
        self.assertEqual(st1.position_y_pct, 20.0)
        self.assertEqual(st1.scale_pct, 100)

        # 4-6 scale updated, position persists
        st2 = segs[2].state_by_source['cam']
        self.assertEqual(st2.position_x_pct, 10.0)
        self.assertEqual(st2.scale_pct, 50.0)

        # 6-10 z updated, others persist
        st3 = segs[3].state_by_source['cam']
        self.assertEqual(st3.z_index, 3.0)
        self.assertEqual(st3.scale_pct, 50.0)

    def test_build_chunks_intersection(self):
        src = VideoSource(
            name='cam',
            file='dummy.mp4',
            clap_time=0.0,
            default_state=SourceState(
                z_index=0,
                position_x_pct=0,
                position_y_pct=0,
                scale_pct=100,
                crop_left_pct=0,
                crop_right_pct=0,
                crop_top_pct=0,
                crop_bottom_pct=0,
            ),
            timeline=[TimelineEvent(at=5.0, z_index=2.0)],
        )
        segs = build_state_segments([src], production_start=0.0, production_end=10.0)
        inc = parse_includes({'x': [2.0, 8.0]}, production_start=0.0, production_end=10.0)
        chunks = build_chunks(segs, inc)
        # should split at 5.0: [2,5] and [5,8]
        self.assertEqual(len(chunks), 2)
        self.assertAlmostEqual(chunks[0].start, 2.0)
        self.assertAlmostEqual(chunks[0].end, 5.0)
        self.assertAlmostEqual(chunks[1].start, 5.0)
        self.assertAlmostEqual(chunks[1].end, 8.0)


if __name__ == '__main__':
    unittest.main()
