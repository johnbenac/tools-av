import json
import subprocess
import tempfile
import unittest
from pathlib import Path


def run(cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(path),
        ],
        text=True,
    ).strip()
    return float(out)


class TestIntegrationSmoke(unittest.TestCase):
    def test_render_small_project(self):
        repo_root = Path(__file__).resolve().parents[1]
        av_editor_bin = repo_root / 'av-editor'

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            master_audio = td / 'master.m4a'
            cam_a = td / 'cam_a.mp4'
            cam_b = td / 'cam_b.mp4'
            out_mp4 = td / 'out.mp4'

            # 6s audio + 6s video sources
            run([
                'ffmpeg', '-v', 'error', '-y',
                '-f', 'lavfi', '-i', 'sine=frequency=220:sample_rate=48000:duration=6',
                '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
                str(master_audio),
            ])

            run([
                'ffmpeg', '-v', 'error', '-y',
                '-f', 'lavfi', '-i', 'color=c=red:s=320x180:r=30:d=6',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                str(cam_a),
            ])
            run([
                'ffmpeg', '-v', 'error', '-y',
                '-f', 'lavfi', '-i', 'color=c=blue:s=320x180:r=30:d=6',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                str(cam_b),
            ])

            config = {
                'master_audio': {
                    'file': str(master_audio),
                    'clap_time': 0.5,
                },
                'video_sources': {
                    'A': {
                        'file': str(cam_a),
                        'clap_time': 0.5,
                        'z_index': 0,
                    },
                    'B': {
                        'file': str(cam_b),
                        'clap_time': 0.5,
                        'z_index': 1,
                        'scale': 50,
                        'position': [25, 25],
                        'timeline': [
                            {'at': 3.0, 'z_index': -1},
                        ],
                    },
                },
                'production': {
                    'start': 0.0,
                    'end': 6.0,
                    'output_file': str(out_mp4),
                    'width': 320,
                    'height': 180,
                    'includes': {},
                },
            }
            cfg_path = td / 'cfg.json'
            cfg_path.write_text(json.dumps(config), encoding='utf-8')

            run(['python3', str(av_editor_bin), 'render', str(cfg_path), '--force'], cwd=str(repo_root))

            self.assertTrue(out_mp4.exists())
            dur = ffprobe_duration(out_mp4)
            # Allow small muxing/encoder rounding differences.
            self.assertTrue(5.5 <= dur <= 6.5, f"duration was {dur}")

    def test_render_includes_cutlist(self):
        repo_root = Path(__file__).resolve().parents[1]
        av_editor_bin = repo_root / 'av-editor'

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            master_audio = td / 'master.m4a'
            cam = td / 'cam.mp4'
            out_mp4 = td / 'out_cut.mp4'

            run([
                'ffmpeg', '-v', 'error', '-y',
                '-f', 'lavfi', '-i', 'sine=frequency=110:sample_rate=48000:duration=10',
                '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
                str(master_audio),
            ])
            run([
                'ffmpeg', '-v', 'error', '-y',
                '-f', 'lavfi', '-i', 'color=c=green:s=320x180:r=30:d=10',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                str(cam),
            ])

            config = {
                'master_audio': {'file': str(master_audio), 'clap_time': 0.0},
                'video_sources': {
                    'cam': {'file': str(cam), 'clap_time': 0.0, 'z_index': 0},
                },
                'production': {
                    'start': 0.0,
                    'end': 10.0,
                    'output_file': str(out_mp4),
                    'width': 320,
                    'height': 180,
                    'includes': {
                        'intro': [0.0, 2.0],
                        'outro': [8.0, 10.0],
                    },
                },
            }
            cfg_path = td / 'cfg.json'
            cfg_path.write_text(json.dumps(config), encoding='utf-8')

            run(['python3', str(av_editor_bin), 'render', str(cfg_path), '--force'], cwd=str(repo_root))

            self.assertTrue(out_mp4.exists())
            dur = ffprobe_duration(out_mp4)
            self.assertTrue(3.5 <= dur <= 4.5, f"duration was {dur}")


if __name__ == '__main__':
    unittest.main()
