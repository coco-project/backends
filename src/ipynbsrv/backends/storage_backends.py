from ipynbsrv.common.utils import FileSystem
from ipynbsrv.contract.backends import StorageBackend
from ipynbsrv.contract.errors import *
from pathlib import Path


class LocalFileSystem(StorageBackend):
    '''
    Storage backend implementation using the local filesystem as the underlaying backend.
    '''

    '''
    :inherit
    '''
    def __init__(self, base_dir):
        super(LocalFileSystem, self).__init__(base_dir)
        self._fs = FileSystem(base_dir)

    '''
    :inherit
    '''
    def dir_exists(self, dir_name, **kwargs):
        try:
            return self._fs.exists(dir_name) and self._fs.is_dir(dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)

    '''
    :inherit
    '''
    def get_dir_group(self, dir_name, **kwargs):
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        try:
            return self._fs.get_group(dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)

    '''
    :inherit
    '''
    def get_dir_mode(self, dir_name, **kwargs):
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        try:
            return self._fs.get_mode(dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)

    '''
    :inherit
    '''
    def get_dir_owner(self, dir_name, **kwargs):
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        try:
            return self._fs.get_owner(dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)

    '''
    :inherit
    '''
    def get_full_dir_path(self, dir_name, **kwargs):
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        try:
            return self._fs.get_full_path(dir_name).as_posix()
        except Exception as ex:
            raise StorageBackendError(ex)

    '''
    :inherit
    '''
    def mk_dir(self, dir_name, **kwargs):
        try:
            self._fs.mk_dir(dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)

    '''
    :inherit

    :param recursive: If true, recursively remove the dir.
                      If false and the directory is not empty, an error is raised.
    '''
    def rm_dir(self, dir_name, **kwargs):
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        recursive = kwargs.get('recursive')
        try:
            if recursive is True:
                self._fs.rrm_dir(dir_name)
            else:
                self._fs.rm_dir(dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)

    '''
    :inherit
    '''
    def set_dir_group(self, dir_name, group, **kwargs):
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        raise NotImplementedError

    '''
    :inherit
    '''
    def set_dir_mode(self, dir_name, mode, **kwargs):
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        try:
            self._fs.set_mode(dir_name, mode)
        except Exception as ex:
            raise StorageBackendError(ex)

    '''
    :inherit
    '''
    def set_dir_owner(self, dir_name, owner, **kwargs):
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        raise NotImplementedError
