from ipynbsrv.common.utils import FileSystem
from ipynbsrv.contract.backends import StorageBackend
from ipynbsrv.contract.errors import DirectoryNotFoundError, StorageBackendError


class LocalFileSystem(StorageBackend):

    """
    Storage backend implementation using the local filesystem as the underlaying backend.
    """

    def __init__(self, base_dir):
        """
        :inherit.
        """
        super(LocalFileSystem, self).__init__(base_dir)
        self._fs = FileSystem(base_dir)

    def dir_exists(self, dir_name, **kwargs):
        """
        :inherit.
        """
        try:
            return self._fs.exists(dir_name) and self._fs.is_dir(dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)

    def get_dir_group(self, dir_name, **kwargs):
        """
        :inherit.
        """
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        try:
            return self._fs.get_group(dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)

    def get_dir_mode(self, dir_name, **kwargs):
        """
        :inherit.
        """
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        try:
            return self._fs.get_mode(dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)

    def get_dir_owner(self, dir_name, **kwargs):
        """
        :inherit.
        """
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        try:
            return self._fs.get_owner(dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)

    def get_full_dir_path(self, dir_name, **kwargs):
        """
        :inherit.
        """
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        try:
            return self._fs.get_full_path(dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)

    def mk_dir(self, dir_name, **kwargs):
        """
        :inherit.
        """
        try:
            self._fs.mk_dir(dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)

    def rm_dir(self, dir_name, **kwargs):
        """
        :inherit.

        :param recursive: If true, recursively remove the dir.
                          If false and the directory is not empty, an error is raised.
        """
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

    def set_dir_group(self, dir_name, group, **kwargs):
        """
        :inherit.
        """
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        try:
            self._fs.set_group(group, dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)

    def set_dir_mode(self, dir_name, mode, **kwargs):
        """
        :inherit.
        """
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        try:
            self._fs.set_mode(mode, dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)

    def set_dir_owner(self, dir_name, owner, **kwargs):
        """
        :inherit.
        """
        if not self.dir_exists(dir_name):
            raise DirectoryNotFoundError("Directory does not exist.")

        try:
            self._fs.set_owner(owner, dir_name)
        except Exception as ex:
            raise StorageBackendError(ex)
