from docker import Client
from ipynbsrv.contract.backends import *
from ipynbsrv.contract.errors import *
import json
import requests
from requests.exceptions import RequestException


class Docker(CloneableContainerBackend, ImageBasedContainerBackend,
             SnapshotableContainerBackend, SuspendableContainerBackend):

    """
    Docker container backend powered by docker-py bindings.
    """

    """
    Unique key used to identify a resource (container, image) returned by the backend.
    """
    IDENTIFIER_KEY = 'Id'

    """
    String to identify from a container's status field either he's paused or not.
    """
    PAUSED_IDENTIFIER = '(Paused)'

    """
    String to identify from a container's status field either he's running or stopped.
    """
    RUNNING_IDENTIFIER = 'Up'

    """
    Prefix for created container snapshots.
    """
    SNAPSHOT_PREFIX = 'snapshot_'

    """
    Unique key used to identify a container's status.
    """
    STATUS_KEY = 'Status'

    def __init__(self, version, base_url='unix://var/run/docker.sock'):
        """
        Initialize a new Docker container backend.

        :param version: The Docker API version number.
        :param base_url: The URL or unix path to the Docker API endpoint.
        """
        try:
            self._client = Client(base_url=base_url, version=version)
        except Exception as ex:
            raise ConnectionError(ex)

    def clone_container(self, container, clone, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        raise NotImplementedError

    def container_exists(self, container, **kwargs):
        """
        :inherit.
        """
        containers = self.get_containers(only_running=False)
        return next((ct for ct in containers if container == ct.get(Docker.IDENTIFIER_KEY)), False) is not False

    def container_exists_by_name(self, name):
        """
        Check if a container with the given name exists.

        :param name: The name to check for.
        """
        containers = self.get_containers(only_running=False)
        for container in containers:
            for ct_name in container.get('Names'):
                if ct_name.replace('/', 00) == name:
                    return True

        return False

    def container_is_running(self, container, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        container = self.get_container(container)
        return container.get(Docker.STATUS_KEY).startswith(Docker.RUNNING_IDENTIFIER)

    def container_is_suspended(self, container, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        container = self.get_container(container)
        return container.get(Docker.STATUS_KEY).endswith(Docker.PAUSED_IDENTIFIER)

    def container_snapshot_exists(self, container, snapshot, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        snapshots = self.get_container_snapshots(container)
        return next((sh for sh in snapshots if snapshot == sh.get(Docker.IDENTIFIER_KEY)), False)

    def create_container(self, specification, **kwargs):
        """
        :inherit.

        :param specification: A dict with the fields as per get_required_container_creation_fields.
        :param kwargs: Optional arguments for docker-py's create_container method.
        """
        self.validate_container_creation_specification(specification)
        if self.container_exists_by_name(container):
            raise ContainerBackendError("A container with that name already exists")

        try:
            container = self._client.create_container(
                name=specification.get('name'),
                image=specification.get('image'),
                command=specification.get('command'),
                ports=kwargs.get('ports'),
                volumes=kwargs.get('volumes'),
                environment=kwargs.get('env'),
                # TODO: other optional params
                detach=True
            )
            return container.get(Docker.IDENTIFIER_KEY)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def create_container_snapshot(self, container, specification, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError
        # if self.container_snapshot_exists(container, name):
        #     raise ContainerBackendError("A snapshot with that name already exists for the given container.")

        self.validate_container_snapshot_creation_specification(specification)
        try:
            container = self.get_container(container)
            snapshot = self._client.commit(
                container=container,
                repository=container.get('Names')[0].replace('/', ''),
                tag=Docker.SNAPSHOT_PREFIX + specification.get('name')
            )
            return snapshot.get(Docker.IDENTIFIER_KEY)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def delete_container(self, container, **kwargs):
        """
        :inherit.

        :param force: If true, the container doesn't need to be stopped first.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError
        force = kwargs.get('force')
        if force is not True and self.container_is_running(container):
            raise IllegalContainerStateError

        try:
            return self._client.remove_container(container=container, force=(force is True))
        except Exception as ex:
            raise ContainerBackendError(ex)

    def delete_container_snapshot(self, container, snapshot, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError
        if not self.container_snapshot_exists(container, snapshot):
            raise ContainerSnapshotNotFoundError

        try:
            return self._client.remove_image(snapshot)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def delete_image(self, image, **kwargs):
        """
        :inherit.
        """
        if not self.image_exists(image):
            raise ContainerImageNotFoundError

        force = kwargs.get('force')
        try:
            self._client.remove_image(image=image, force=(force is True))
        except Exception as ex:
            raise ContainerBackendError(ex)

    def exec_in_container(self, container, cmd, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError
        if not self.container_is_running(container) or self.container_is_suspended(container):
            raise IllegalContainerStateError

        try:
            exec_id = self._client.exec_create(container=container, cmd=cmd)
            return self._client.exec_start(exec_id=exec_id, stream=False)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_container(self, container, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        containers = self.get_containers(only_running=False)
        return next(ct for ct in containers if container == ct.get(Docker.IDENTIFIER_KEY))

    def get_container_logs(self, container, **kwargs):
        """
        :inherit.

        :param timestamps: If true, the log messages' timestamps are included.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        timestamps = kwargs.get('timestamps')
        try:
            logs = self._client.logs(
                container=container,
                stream=False,
                timestamps=(timestamps is True)
            )
            return filter(lambda x: len(x) > 0, logs.split('\n'))  # remove empty lines
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_container_snapshot(self, container, snapshot, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError
        if not self.container_snapshot_exists(container, snapshot):
            raise ContainerSnapshotNotFoundError

        snapshots = self.get_container_snapshots(container)
        return next(sh for sh in snapshots if snapshot == sh.get(Docker.IDENTIFIER_KEY))

    def get_container_snapshots(self, container, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        container_name = self.get_container(container).get('Names')[0].replace('/', '')
        try:
            snapshots = []
            for snapshot in self._client.images():
                for repotag in snapshot.get('RepoTags'):
                    if repotag.startswith('%s:%s' % (container_name, Docker.SNAPSHOT_PREFIX)):
                        # add required fields as per API specification
                        snapshot[ContainerBackend.FIELD_PK] = snapshot.get(Docker.IDENTIFIER_KEY)

                        snapshots.append(snapshot)
            return snapshots
        except:
            raise ContainerBackendError(ex)

    def get_containers(self, only_running=False, **kwargs):
        """
        :inherit.
        """
        try:
            containers = self._client.containers(all=(not only_running))
            for container in containers:
                # add required fields as per API specification
                container[ContainerBackend.FIELD_PK] = container.get(Docker.IDENTIFIER_KEY)
                status = ContainerBackend.STATUS_RUNNING
                # TODO: use is_running and is_suspended methods. recursion
                if not container.get(Docker.STATUS_KEY).startswith(Docker.RUNNING_IDENTIFIER):
                    status = ContainerBackend.STATUS_STOPPED
                elif container.get(Docker.STATUS_KEY).endswith(Docker.PAUSED_IDENTIFIER):
                    status = SuspendableContainerBackend.STATUS_SUSPENDED
                container[ContainerBackend.FIELD_STATUS] = status
            return containers
        except Exception as ex:
            print ex
            raise ContainerBackendError(ex)

    def get_image(self, image, **kwargs):
        """
        :inherit.
        """
        if not self.image_exists(image):
            raise ContainerImageNotFoundError

        images = self.get_images()
        return next(img for img in images if image == img.get(Docker.IDENTIFIER_KEY))

    def get_images(self, **kwargs):
        """
        :inherit.
        """
        try:
            images = self._client.images()
            for image in images:
                # add required fields as per API specification
                image[ContainerBackend.FIELD_PK] = image.get(Docker.IDENTIFIER_KEY)
            return images
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_required_container_creation_fields(self):
        """
        :inherit.
        """
        return [
            ('name', basestring),
            ('image', basestring),
            ('command', basestring)
        ]

    def get_required_container_start_fields(self):
        """
        :inherit.
        """
        return [
            ('identifier', basestring)
        ]

    def get_required_snapshot_creation_fields(self):
        """
        :inherit.
        """
        return [
            ('name', basestring)
        ]

    def get_status(self):
        """
        :inherit.
        """
        try:
            self._client.info()
            return ContainerBackend.BACKEND_STATUS_OK
        except Exception:
            return ContainerBackend.BACKEND_STATUS_ERROR

    def image_exists(self, image, **kwargs):
        """
        :inherit.
        """
        images = self.get_images()
        return next((img for img in images if image == img.get(Docker.IDENTIFIER_KEY)), False)

    def restart_container(self, container, **kwargs):
        """
        :inherit.

        :param force: If true, kill the container if it doesn't want to stop.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        force = kwargs.get('force')
        try:
            if force:
                return self._client.restart(container=container, timeout=0)
            else:
                return self._client.restart(container=container)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def restore_container_snapshot(self, container, snapshot, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError
        if not self.container_snapshot_exists(container, snapshot):
            raise ContainerSnapshotNotFoundError

        raise NotImplementedError

    def resume_container(self, container, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError
        if not self.container_is_running(container) or not self.container_is_suspended(container):
            raise IllegalContainerStateError

        try:
            return self._client.unpause(container=container)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def start_container(self, container, **kwargs):
        """
        :inherit.

        :param kwargs: All optional arguments the docker-py library accepts as well.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError
        if self.container_is_running(container):
            raise IllegalContainerStateError

        try:
            return self._client.start(container=container, **kwargs)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def stop_container(self, container, **kwargs):
        """
        :inherit.

        :param force: If true, kill the container if it doesn't want to stop.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError
        if not self.container_is_running(container):
            raise IllegalContainerStateError

        force = kwargs.get('force')
        try:
            if force:
                return self._client.stop(container=container, timeout=0)
            else:
                return self._client.stop(container=container)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def suspend_container(self, container, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError
        if not self.container_is_running(container) or self.container_is_suspended(container):
            raise IllegalContainerStateError

        try:
            return self._client.pause(container=container)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def validate_container_creation_specification(self, specification):
        """
        Validate that the specification matches the definition.

        :param specification: The specification to validate.
        """
        for rname, rtype in self.get_required_container_creation_fields():
            field = specification.get(rname)
            if field is None:
                raise IllegalContainerSpecificationError("Required field %s missing." % rname)
            elif not isinstance(field, rtype):
                raise IllegalContainerSpecificationError("Required field %s of wrong type. %s expected, %s given." % (field, rtype, type(field)))

        return specification

    def validate_container_snapshot_creation_specification(self, specification):
        """
        Validate that the specification matches the definition.

        :param specification: The specification to validate.
        """
        for rname, rtype in self.get_required_snapshot_creation_fields():
            field = specification.get(rname)
            if field is None:
                raise IllegalContainerSpecificationError("Required field %s missing." % rname)
            elif not isinstance(field, rtype):
                raise IllegalContainerSpecificationError("Required field %s of wrong type. %s expected, %s given." % (field, rtype, type(field)))

        return specification


class HttpRemote(CloneableContainerBackend, ImageBasedContainerBackend,
                 SnapshotableContainerBackend, SuspendableContainerBackend):

    """
    The HTTP remote container backend can be used to communicate with a HTTP remote host API.

    It is therefor considered an intermediate backend, as it does not operate on a backend directly.
    """

    """
    String that can be used as a placeholder in slugs to be replaced by the containers identifier.
    """
    PLACEHOLDER_CONTAINER = '<container>'

    def __init__(self, url, slugs=None):
        """
        Initialize a new HTTP remote container backend.

        :param url: The base URL of the API endpoint (e.g. http://my.remote.ip:8080)
        :param slugs: A dictionary of slugs where the various endpoints can be found (e.g. /containers for containers)
        """
        if slugs:
            if isinstance(slugs, dict):
                self.slugs.update(slugs)
            else:
                raise ValueError("Slugs need to be a dictionary")
        self.url = url
        self.slugs = {
            'containers': '/containers',
            'snapshots': '/containers/<container>/snapshots',
            'images': '/containers/images'
        }

    def clone_container(self, container, **kwargs):
        """
        :inherit.
        """
        raise NotImplementedError

    def container_exists(self, container, **kwargs):
        """
        :inherit.
        """
        try:
            self.get_container(container)
            return True
        except NotFounderror:
            return False
        except Exception as ex:
            raise ex

    def container_is_running(self, container, **kwargs):
        """
        :inherit.
        """
        container = self.get_container(container)
        return container.get(ContainerBackend.FIELD_STATUS) == ContainerBackend.STATUS_RUNNING

    def container_is_suspended(self, container, **kwargs):
        """
        :inherit.
        """
        container = self.get_container(container)
        return container.get(ContainerBackend.FIELD_STATUS) == SuspendableContainerBackend.STATUS_SUSPENDED

    def container_snapshot_exists(self, container, snapshot, **kwargs):
        """
        :inherit.
        """
        try:
            self.get_container_snapshot(container, snapshot)
            return True
        except NotFounderror:
            return False
        except Exception as ex:
            raise ex

    def create_container(self, specification, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.post(
                url=self.url + self.slugs.get('containers'),
                data=json.dumps(specification)
            )
            if response.status_code == requests.codes.created:
                return response.json()
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def create_container_snapshot(self, container, specification, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.post(
                url=self.generate_container_snapshots_url(container),
                data=json.dumps(specification)
            )
            if response.status_code == requests.codes.created:
                return response.json()
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def create_image(self, specification, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.post(
                url=self.url + self.slugs.get('images'),
                data=json.dumps(specification)
            )
            if response.status_code == requests.codes.created:
                return response.json()
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def delete_container(self, container, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.delete(url=self.generate_container_url(container))
            if response.status_code == requests.codes.no_content:
                return True
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def delete_container_snapshot(self, container, snapshot, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.delete(url=self.generate_container_snapshot_url(container, snapshot))
            if response.status_code == requests.codes.no_content:
                return True
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def delete_image(self, image, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.delete(url=self.generate_image_url(image))
            if response.status_code == requests.codes.no_content:
                return True
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def exec_in_container(self, container, cmd, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.post(
                url=self.generate_container_url(container) + '/exec',
                data=json.dumps({
                    'command': cmd
                })
            )
            if response.status_code == requests.codes.ok:
                return response.json()
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def generate_container_url(self, container):
        """
        Generate the full URL with which the container resource can be accessed on the remote API.

        :param container: The container identifier to generate the URL for.
        """
        return self.url + self.slugs.get('containers') + '/' + container

    def generate_container_snapshot_url(self, container, snapshot):
        """
        Generate the full URL with which the container's snapshot resource can be accessed on the remote API.

        :param container: The container identifier to generate the snapshot URL for.
        :param snapshot: The snapshot identifier to generate the snapshot URL for.
        """
        return self.url + self.slugs.get('snapshots').replace(HttpRemote.PLACEHOLDER_CONTAINER, container) + '/' + snapshot

    def generate_container_snapshots_url(self, container):
        """
        Generate the full URL with which the container's snapshot resource can be accessed on the remote API.

        :param container: The container identifier to generate the snapshots URL for.
        """
        return self.url + self.slugs.get('snapshots').replace(HttpRemote.PLACEHOLDER_CONTAINER, container)

    def generate_image_url(self, image):
        """
        Generate the full URL with which the image resource can be accessed on the remote API.

        :param image: The image identifier to generate the URL for.
        """
        return self.url + self.slugs.get('images') + '/' + image

    def get_container(self, container, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.get(url=self.generate_container_url(container))
            if response.status_code == requests.codes.ok:
                return response.json()
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_container_logs(self, container, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.get(url=self.generate_container_url(container) + '/logs')
            if response.status_code == requests.codes.ok:
                return response.json()
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_container_snapshot(self, container, snapshot, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.get(url=self.generate_container_snapshot_url(container, snapshot))
            if response.status_code == requests.codes.ok:
                return response.json()
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_container_snapshots(self, container, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.get(url=self.generate_container_snapshots_url(container))
            if response.status_code == requests.codes.ok:
                return response.json()
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ContainerBackendError(ex)

    def get_containers(self, only_running=False, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.get(url=self.url + self.slugs.get('containers'))
            if response.status_code == requests.codes.ok:
                return response.json()
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_image(self, image, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.get(url=self.generate_image_url(image))
            if response.status_code == requests.codes.ok:
                return response.json()
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_images(self, image, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.get(url=self.url + self.slugs.get('images'))
            if response.status_code == requests.codes.ok:
                return response.json()
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ContainerBackendError(ex)

    def get_required_container_creation_fields(self):
        """
        :inherit.
        """
        raise NotImplementedError

    def get_required_container_start_fields(self):
        """
        :inherit.
        """
        raise NotImplementedError

    def get_required_image_creation_fields(self):
        """
        :inherit.
        """
        raise NotImplementedError

    def get_required_snapshot_creation_fields(self):
        """
        :inherit.
        """
        raise NotImplementedError

    def get_status(self):
        """
        :inherit.
        """
        try:
            response = requests.get(url=self.url + '/health')
            if response.status_code == requests.codes.ok:
                return response.json().get('backends').get('container').get('status')
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def image_exists(self, image):
        """
        :inherit.
        """
        try:
            self.get_image(image)
            return True
        except NotFoundError:
            return False
        except Exception as ex:
            raise ContainerBackendError(ex)

    @staticmethod
    def raise_status_code_error(status_code):
        """
        TODO: write doc.
        """
        if status_code == requests.codes.bad_request:              # 400
            raise NotImplementedError
        elif status_code == requests.codes.not_found:              # 404
            raise ContainerINotFoundError
        elif status_code == requests.codes.method_not_allowed:     # 405
            raise NotImplementedError
        elif status_code == requests.codes.request_timeout:        # 408
            raise NotImplementedError
        elif status_code == requests.codes.precondition_failed:    # 412
            raise IllegalContainerStateError
        elif status_code == requests.codes.unprocessable_entity:   # 422
            raise NotImplementedError
        elif status_code == requests.codes.precondition_required:  # 428
            raise NotImplementedError
        elif status_code == requests.codes.internal_server_error:  # 500
            raise NotImplementedError
        elif status_code == requests.codes.not_implemented:        # 501
            raise NotImplementedError
        else:
            raise NotImplementedError

    def restart_container(self, container, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.post(
                url=self.generate_container_url(container) + '/restart',
                data=json.dumps({})
            )
            if response.status_code == requests.codes.no_content:
                return True
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def restore_container_snapshot(self, container, snapshot, **kwargs):
        """
        :inherit.
        """
        raise NotImplementedError

    def resume_container(self, container, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.post(
                url=self.generate_container_url(container) + '/resume',
                data=json.dumps({})
            )
            if response.status_code == requests.codes.no_content:
                return True
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def start_container(self, container):
        """
        :inherit.
        """
        try:
            response = requests.post(
                url=self.generate_container_url(container) + '/start',
                data=json.dumps({})
            )
            if response.status_code == requests.codes.no_content:
                return True
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def stop_container(self, container, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.post(
                url=self.generate_container_url(container) + '/stop',
                data=json.dumps({})
            )
            if response.status_code == requests.codes.no_content:
                return True
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def suspend_container(self, container, **kwargs):
        """
        :inherit.
        """
        try:
            response = requests.post(
                url=self.generate_container_url(container) + '/suspend',
                data=json.dumps({})
            )
            if response.status_code == requests.codes.no_content:
                return True
            else:
                HttpRemote.raise_status_code_error(response.status_code)
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)
