import math
import http.client
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app
from tools.video_limits import inspect_video


class VideoAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.store = app.JobStore()
        self.store_patch = patch.object(app, 'STORE', self.store)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)

    def start_http_server(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), app.MotionDiffHandler)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        def stop():
            server.shutdown()
            server.server_close()
            thread.join()
        self.addCleanup(stop)
        return server.server_address

    def test_oversize_request_is_rejected_before_body_is_sent(self):
        address = self.start_http_server()
        with patch.object(app, 'MAX_UPLOAD_BYTES', 10):
            connection = http.client.HTTPConnection(*address, timeout=5)
            try:
                connection.putrequest('POST', '/api/analyze')
                connection.putheader('Content-Length', '11')
                connection.endheaders()
                response = connection.getresponse()
                self.assertEqual(response.status, 413)
                response.read()
            finally:
                connection.close()
        self.assertTrue(self.store.reserve())
        self.store.release()

    def test_busy_request_does_not_read_body_or_release_other_job_slot(self):
        address = self.start_http_server()
        self.assertTrue(self.store.reserve())
        connection = http.client.HTTPConnection(*address, timeout=5)
        try:
            connection.putrequest('POST', '/api/analyze')
            connection.putheader('Content-Length', '1')
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 503)
            response.read()
        finally:
            connection.close()
        self.assertFalse(self.store.reserve())
        self.store.release()

    def test_per_file_size_rejected_and_slot_released(self):
        address = self.start_http_server()
        body = (b'--test\r\nContent-Disposition: form-data; name="reference"; filename="r.mp4"\r\n\r\n1234\r\n'
                b'--test\r\nContent-Disposition: form-data; name="student"; filename="s.mp4"\r\n\r\n1\r\n--test--\r\n')
        with patch.object(app, 'MAX_VIDEO_BYTES', 3), patch.object(self.store, 'create') as create:
            connection = http.client.HTTPConnection(*address, timeout=5)
            try:
                connection.request('POST', '/api/analyze', body,
                                   {'Content-Type': 'multipart/form-data; boundary=test'})
                response = connection.getresponse()
                self.assertEqual(response.status, 413)
                response.read()
            finally:
                connection.close()
            create.assert_not_called()
        self.assertTrue(self.store.reserve())
        self.store.release()

    def test_truncated_upload_releases_slot(self):
        import socket
        address = self.start_http_server()
        connection = http.client.HTTPConnection(*address, timeout=5)
        try:
            connection.putrequest('POST', '/api/analyze')
            connection.putheader('Content-Length', '10')
            connection.endheaders()
            connection.send(b'123')
            connection.sock.shutdown(socket.SHUT_WR)
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
        finally:
            connection.close()
        self.assertTrue(self.store.reserve())
        self.store.release()

    def test_duration_boundary_and_invalid_metadata(self):
        for fps, frames, accepted in (
            (30, 1800, True), (30, 1801, False),
            (0, 10, False), (math.nan, 10, False),
            (30, 0, False), (30, math.inf, False), (120, 3601, False),
        ):
            with self.subTest(fps=fps, frames=frames):
                released = []
                capture = SimpleNamespace(isOpened=lambda: True,
                    get=lambda key: fps if key == 'fps' else frames,
                    release=lambda: released.append(True))
                cv2 = SimpleNamespace(VideoCapture=lambda path: capture,
                                      CAP_PROP_FPS='fps', CAP_PROP_FRAME_COUNT='frames')
                if accepted:
                    result = inspect_video('video.mp4', cv2, max_duration_seconds=60, max_frames=3600)
                    self.assertEqual(result['duration_seconds'], 60)
                else:
                    with self.assertRaises(ValueError):
                        inspect_video('video.mp4', cv2, max_duration_seconds=60, max_frames=3600)
                self.assertEqual(released, [True])

    def test_rejected_video_does_not_load_model_and_releases_slot(self):
        import cv2
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = app.JobStore(root)
            self.assertTrue(store.reserve())
            self.assertFalse(store.reserve())
            store._jobs['test'] = {}
            with patch.object(cv2, 'VideoCapture') as decoder:
                decoder.return_value.isOpened.return_value = True
                decoder.return_value.get.side_effect = lambda key: 30 if key == cv2.CAP_PROP_FPS else 1830
                store._run('test', b'reference', b'student', 'ref.mp4', 'student.mp4')
            self.assertEqual(store.get('test')['status'], 'failed')
            self.assertIn('61.00', store.get('test')['error'])
            self.assertFalse((root / 'test/input/reference.mp4').exists())
            self.assertFalse((root / 'test/input/student.mp4').exists())
            self.assertFalse((root / 'test/pose').exists())
            self.assertTrue(store.reserve())
            store.release()

    def test_delete_run_removes_videos_report_and_blocks_old_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = 'a' * 32
            self.store.runs_dir = root
            video = root / run_id / 'input' / 'reference.mp4'
            report = root / run_id / 'report' / 'comparison.md'
            video.parent.mkdir(parents=True)
            report.parent.mkdir()
            video.write_bytes(b'video')
            report.write_text('report', encoding='utf-8')
            self.store._jobs[run_id] = {'created_at': 1, 'status': 'complete'}
            address = self.start_http_server()
            connection = http.client.HTTPConnection(*address, timeout=5)
            try:
                connection.request('POST', f'/api/runs/{run_id}/delete')
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                for path in (f'/runs/{run_id}/input/reference.mp4',
                             f'/runs/{run_id}/report/comparison.md',
                             f'/api/status/{run_id}'):
                    connection.request('GET', path)
                    response = connection.getresponse()
                    self.assertEqual(response.status, 404)
                    response.read()
            finally:
                connection.close()
            self.assertFalse((root / run_id).exists())
            self.assertFalse(self.store._delete_requested)

    def test_expired_run_removes_everything(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = 'b' * 32
            self.store.runs_dir = root
            report = root / run_id / 'report' / 'comparison.md'
            report.parent.mkdir(parents=True)
            report.write_text('report', encoding='utf-8')
            self.store._jobs[run_id] = {'created_at': 1, 'status': 'failed'}
            self.store.cleanup_expired(now=1 + app.RUN_IDLE_TTL_SECONDS)
            self.assertIsNone(self.store.get(run_id))
            self.assertFalse((root / run_id).exists())

    def test_delete_during_processing_removes_files_after_worker_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = 'd' * 32
            store = app.JobStore(root)
            started = threading.Event()
            resume = threading.Event()

            def inspect_and_wait(*args, **kwargs):
                started.set()
                if not resume.wait(5):
                    raise TimeoutError('worker did not resume')
                return {'frames': 1}

            self.assertTrue(store.reserve())
            store._jobs[run_id] = {'created_at': 1, 'status': 'processing'}
            store._running.add(run_id)
            worker = threading.Thread(target=store._run,
                                      args=(run_id, b'reference', b'student', 'r.mp4', 's.mp4'))
            with patch('tools.video_limits.inspect_video', side_effect=inspect_and_wait), \
                    patch.object(app, 'MODEL_PATH', root / 'missing-model'):
                worker.start()
                try:
                    self.assertTrue(started.wait(5))
                    store.delete(run_id)
                    self.assertIsNone(store.get(run_id))
                    self.assertTrue((root / run_id / 'input' / 'reference.mp4').exists())
                finally:
                    resume.set()
                    worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertFalse((root / run_id).exists())
            self.assertFalse(store._delete_requested)
            self.assertTrue(store.reserve())
            store.release()

    def test_startup_cleanup_only_removes_run_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / ('c' * 32)
            unrelated = root / 'keep-me'
            run.mkdir()
            unrelated.mkdir()
            (run / 'report.md').write_text('temporary', encoding='utf-8')
            (unrelated / 'note.txt').write_text('keep', encoding='utf-8')
            with patch.object(app, 'RUNS_DIR', root):
                app.clear_orphaned_runs_on_start()
            self.assertFalse(run.exists())
            self.assertTrue((unrelated / 'note.txt').exists())
