"""Offline regression tests for the shared pinned-archive importer."""
import copy
import hashlib
import io
import tarfile

from helpers import TemporaryTestCase
from scripts.expand_compute_dataset import import_sources


class DatasetImportTests(TemporaryTestCase):
    def setUp(self):
        super().setUp()
        self.data = self.directory / 'data'
        self.archives = self.directory / 'archives'
        self.lock = {'sources': {}}

    def archive(self, repo, entries):
        path = self.archives / repo / 'archive.tar.gz'
        path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(path, 'w:gz') as stream:
            for name, content in entries:
                member = tarfile.TarInfo('snapshot/' + name)
                member.size = len(content)
                stream.addfile(member, io.BytesIO(content))
        return {'revision': 'a' * 40, 'archive_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'files': sorted({name for name, _ in entries}), 'license': 'BSD-2-Clause'}

    def test_import_preserves_existing_inventory_and_is_idempotent(self):
        repo = 'example/design'
        config = self.archive(repo, [('top.v', b'module top; endmodule\n')])
        target = self.data / 'sources' / repo
        target.mkdir(parents=True)
        (target / 'existing.v').write_bytes(b'original')
        self.lock['sources'][repo] = {**config, 'files': {'existing.v': hashlib.sha256(b'original').hexdigest()}}
        for _ in range(2):
            import_sources(self.data, self.lock, self.archives, False, {repo: config})
            self.assertEqual((target / 'existing.v').read_bytes(), b'original')
            source = self.lock['sources'][repo]
            self.assertEqual(set(source['files']), {'existing.v', 'top.v'})
            self.assertEqual(source['license'], 'BSD-2-Clause')
            self.assertEqual(source['files']['top.v'], hashlib.sha256((target / 'top.v').read_bytes()).hexdigest())

    def test_all_archives_checked_before_any_write(self):
        first = self.archive('example/first', [('top.v', b'first')])
        second = self.archive('example/second', [('top.v', b'second')])
        second['archive_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'checksum'):
            import_sources(self.data, self.lock, self.archives, False,
                           {'example/first': first, 'example/second': second})
        self.assertFalse(self.data.exists())
        self.assertEqual(self.lock, {'sources': {}})

    def test_changed_revision_or_original_is_never_overwritten(self):
        repo = 'example/design'
        config = self.archive(repo, [('top.v', b'original')])
        import_sources(self.data, self.lock, self.archives, False, {repo: config})
        locked = copy.deepcopy(self.lock)
        with self.assertRaisesRegex(ValueError, 'revision'):
            import_sources(self.data, self.lock, self.archives, False,
                           {repo: {**config, 'revision': 'b' * 40}})
        source = self.data / 'sources' / repo / 'top.v'
        source.write_bytes(b'local change')
        with self.assertRaisesRegex(ValueError, 'changed original'):
            import_sources(self.data, self.lock, self.archives, False, {repo: config})
        self.assertEqual(source.read_bytes(), b'local change')
        self.assertEqual(self.lock, locked)

    def test_duplicate_or_traversal_entries_are_rejected(self):
        for entries in ([('top.v', b'one'), ('top.v', b'two')], [('../escape.v', b'bad')]):
            with self.subTest(entries=entries):
                config = self.archive('example/design', entries)
                with self.assertRaises(ValueError):
                    import_sources(self.data, self.lock, self.archives, False, {'example/design': config})
                self.assertFalse(self.data.exists())
