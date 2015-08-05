from docker import Client, utils as docker_utils
from docker.errors import APIError as DockerError
from ipynbsrv.contract.backends import *
from ipynbsrv.contract.errors import *
import json
import re
import requests
from requests.exceptions import RequestException
import time


class Docker(SnapshotableContainerBackend, SuspendableContainerBackend):

    """
    Docker container backend powered by docker-py bindings.
    """

    """
    The prefix that is prepended to the name of created containers.
    """
    CONTAINER_NAME_PREFIX = 'ipynbsrv-'

    """
    The prefix that is prepended to the name of created container snapshots.
    """
    CONTAINER_SNAPSHOT_NAME_PREFIX = 'snapshot-'

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

    def container_exists(self, container, **kwargs):
        """
        :inherit.
        """
        try:
            self._client.inspect_container(container)
            return True
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                return False
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def container_image_exists(self, image, **kwargs):
        """
        :inherit.
        """
        try:
            image = self._client.inspect_image(image)
            return True
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                return False
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def container_is_running(self, container, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        try:
            return self._client.inspect_container(container).get('State', {}).get('Running', {}) is True
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerNotFoundError
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def container_is_suspended(self, container, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        try:
            return self._client.inspect_container(container).get('State', {}).get('Paused', {}) is True
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerNotFoundError
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def container_snapshot_exists(self, snapshot, **kwargs):
        """
        :inherit.
        """
        return self.container_image_exists(snapshot, **kwargs)

    def create_container(self, name, ports, volumes, cmd=None, image=None, clone_of=None, **kwargs):
        """
        :inherit.
        """
        name = self.CONTAINER_NAME_PREFIX + name
        if self.container_exists(name):
            raise ContainerBackendError("A container with that name already exists")
        if clone_of is not None and not self.container_exists(clone_of):
            raise ContainerNotFoundError("Base container for the clone does not exist")

        # cloning
        if clone_of is None:
            image_pk = image
        else:
            # TODO: some way to ensure no regular image is created with that name
            image = self.create_container_image(clone_of, 'for-clone-' + name + '-at-' + str(int(time.time())))
            image_pk = image.get(ContainerBackend.KEY_PK)
        # bind mounts
        mount_points = [vol.get(ContainerBackend.VOLUME_KEY_TARGET) for vol in volumes]
        binds = map(
            lambda bind: "%s:%s" % (
                bind.get(ContainerBackend.VOLUME_KEY_SOURCE),
                bind.get(ContainerBackend.VOLUME_KEY_TARGET)
            ),
            volumes
        )
        # port mappings
        port_mappings = {}
        for port in ports:
            port_mappings[port.get(ContainerBackend.PORT_MAPPING_KEY_INTERNAL)] = (
                port.get(ContainerBackend.PORT_MAPPING_KEY_ADDRESS),
            )

        container = None
        try:
            container = self._client.create_container(
                image=image_pk,
                command=cmd,
                name=name,
                ports=[port.get(ContainerBackend.PORT_MAPPING_KEY_INTERNAL) for port in ports],
                volumes=mount_points,
                host_config=docker_utils.create_host_config(
                    binds=binds,
                    port_bindings=port_mappings
                ),
                environment=kwargs.get('env'),
                detach=True
            )
            container = self.get_container(container.get('Id'))
            self.start_container(container.get(ContainerBackend.KEY_PK))
        except Exception as ex:
            raise ContainerBackendError(ex)

        if clone_of is None:
            ret = container
        else:
            ret = {
                ContainerBackend.CONTAINER_KEY_CLONE_CONTAINER: container,
                ContainerBackend.CONTAINER_KEY_CLONE_IMAGE: image
            }
        return ret

    def create_container_image(self, container, name, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError
        image_name = self.get_internal_container_image_name(container, name)
        if self.container_image_exists(image_name):
            raise ContainerBackendError("An image with that name already exists for the given container")

        try:
            image = self._client.commit(
                container=container,
                repository=image_name.split(':')[0],
                tag=image_name.split(':')[1]
            )
            return self.get_container_image(image.get('Id'))
        except Exception as ex:
            raise ContainerBackendError(ex)

    def create_container_snapshot(self, container, name, **kwargs):
        """
        :inherit.
        """
        return self.create_container_image(container, self.CONTAINER_SNAPSHOT_NAME_PREFIX + name)

    def delete_container(self, container, force=False, **kwargs):
        """
        :inherit.

        :param force: If true, the container doesn't need to be stopped first.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError
        if force is not True and self.container_is_running(container):
            raise IllegalContainerStateError

        try:
            return self._client.remove_container(container=container, force=(force is True))
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerNotFoundError
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def delete_container_image(self, image, force=False, **kwargs):
        """
        :inherit.

        TODO: raises error: 409 Client Error: Conflict ("Conflict, cannot delete ... because the container ... is using it, use -f to force")
        """
        if not self.container_image_exists(image):
            raise ContainerImageNotFoundError

        try:
            self._client.remove_image(image=image, force=True)  # force=(force is True)
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerImageNotFoundError
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def delete_container_snapshot(self, snapshot, force=False, **kwargs):
        """
        :inherit.

        TODO: raises error: 409 Client Error: Conflict ("Conflict, cannot delete ... because the container ... is using it, use -f to force")
        """
        try:
            self.delete_container_image(snapshot, force=True, **kwargs)
        except ContainerImageNotFoundError as ex:
            raise ContainerSnapshotNotFoundError
        except ContainerBackendError as ex:
            raise ex
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
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerNotFoundError
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_container(self, container, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        try:
            container = self._client.inspect_container(container)
            return self.make_container_contract_conform(container)
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerNotFoundError
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_container_image(self, image, **kwargs):
        """
        :inherit.
        """
        if not self.container_image_exists(image):
            raise ContainerImageNotFoundError

        try:
            image = self._client.inspect_image(image)
            return self.make_image_contract_conform(image)
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerImageNotFoundError
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_container_images(self, **kwargs):
        """
        :inherit.
        """
        try:
            images = []
            for image in self._client.images():
                if not self.is_container_snapshot(image):
                    images.append(self.make_image_contract_conform(image))
            return images
        except Exception as ex:
            raise ContainerBackendError(ex)

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
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerNotFoundError
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_container_port_mappings(self, container, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        try:
            container = self._client.inspect_container(container)
            container_ports = container.get('HostConfig', {}).get('PortBindings', {})
            ports = []
            if container_ports is not None:
                for port, mappings in container_ports.items():
                    for mapping in mappings:
                        address = mapping.get('HostIp')
                        if len(address) == 0:
                            address = '0.0.0.0'
                        ports.append({
                            ContainerBackend.PORT_MAPPING_KEY_ADDRESS: address,
                            ContainerBackend.PORT_MAPPING_KEY_EXTERNAL: mapping.get('HostPort'),
                            ContainerBackend.PORT_MAPPING_KEY_INTERNAL: port
                        })
            return ports
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerNotFoundError
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_container_snapshot(self, snapshot, **kwargs):
        """
        :inherit.
        """
        if not self.container_snapshot_exists(snapshot):
            raise ContainerSnapshotNotFoundError

        return next(sh for sh in self.get_container_snapshots() if sh.get(ContainerBackend.KEY_PK).startswith(snapshot))

    def get_internal_container_image_name(self, container, name):
        """
        Return the name how the image with name `name` for the given container is named internally.

        :param container: The container the snapshot belongs to.
        :param name: The image's name.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        try:
            container = self._client.inspect_container(container)
            container_name = container.get('Name')
            return re.sub(
                # i.e. ipynbsrv-u2500-ipython
                r'^/' + self.CONTAINER_NAME_PREFIX + r'u(\d+)-(.+)$',
                # i.e. ipynbsrv-u2500/ipython:shared-name
                self.CONTAINER_NAME_PREFIX + r'u\g<1>' + '/' + r'\g<2>' + ':' + name,
                container_name
            )
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerNotFoundError
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_container_snapshots(self, **kwargs):
        """
        :inherit.
        """
        try:
            snapshots = []
            for image in self._client.images():
                if self.is_container_snapshot(image):
                    snapshots.append(self.make_snapshot_contract_conform(image))
            return snapshots
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_containers(self, only_running=False, **kwargs):
        """
        :inherit.
        """
        try:
            containers = []
            for container in self._client.containers(all=(not only_running)):
                containers.append(self.make_container_contract_conform(container))
            return containers
        except Exception as ex:
            raise ContainerBackendError(ex)

    def get_containers_snapshots(self, container, **kwargs):
        """
        TODO: implement.
        """
        raise NotImplementedError

    def get_status(self):
        """
        :inherit.
        """
        try:
            self._client.info()
            return ContainerBackend.BACKEND_STATUS_OK
        except Exception:
            return ContainerBackend.BACKEND_STATUS_ERROR

    def is_container_snapshot(self, image):
        """
        Return true if `image` is internally used as a container snapshot.

        :param image: The image to check.
        """
        parts = image.get('RepoTags', [' : '])[0].split(':')
        if len(parts) > 1:
            return parts[1].startswith(self.CONTAINER_SNAPSHOT_NAME_PREFIX)
        return False

    def make_container_contract_conform(self, container):
        """
        Ensure the container dict returned from Docker is confirm with that the contract requires.

        :param container: The container to make conform.
        """
        if not self.container_is_running(container.get('Id')):
            status = ContainerBackend.CONTAINER_STATUS_STOPPED
        elif self.container_is_suspended(container.get('Id')):
            status = SuspendableContainerBackend.CONTAINER_STATUS_SUSPENDED
        else:
            status = ContainerBackend.CONTAINER_STATUS_RUNNING

        return {
            ContainerBackend.KEY_PK: container.get('Id'),
            ContainerBackend.CONTAINER_KEY_PORT_MAPPINGS: self.get_container_port_mappings(container.get('Id')),
            ContainerBackend.CONTAINER_KEY_STATUS: status
        }

    def make_image_contract_conform(self, image):
        """
        Ensure the image dict returned from Docker is confirm with that the contract requires.

        :param image: The image to make conform.
        """
        return {
            ContainerBackend.KEY_PK: image.get('Id')
        }

    def make_snapshot_contract_conform(self, snapshot):
        """
        Ensure the snapshot dict returned from Docker is confirm with that the contract requires.

        :param snapshot: The snapshot to make conform.
        """
        return self.make_image_contract_conform(snapshot)

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
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerImageNotFoundError
            raise ContainerBackendError(ex)
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
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerImageNotFoundError
            raise ContainerBackendError(ex)
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
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerImageNotFoundError
            raise ContainerBackendError(ex)
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
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerImageNotFoundError
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)


class HttpRemote(SnapshotableContainerBackend, SuspendableContainerBackend):

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
            'container_snapshots': '/containers/<container>/snapshots',
            'snapshots': '/containers/snapshots',
            'images': '/containers/images'
        }

    def container_exists(self, container, **kwargs):
        """
        :inherit.
        """
        try:
            self.get_container(container)
            return True
        except ContainerNotFoundError:
            return False
        except Exception as ex:
            raise ex

    def container_image_exists(self, image, **kwargs):
        """
        :inherit.
        """
        try:
            self.get_container_image(image)
            return True
        except ContainerImageNotFoundError:
            return False
        except Exception as ex:
            raise ex

    def container_is_running(self, container, **kwargs):
        """
        :inherit.
        """
        container = self.get_container(container)
        return container.get(ContainerBackend.CONTAINER_KEY_STATUS) == ContainerBackend.CONTAINER_STATUS_RUNNING

    def container_is_suspended(self, container, **kwargs):
        """
        :inherit.
        """
        container = self.get_container(container)
        return container.get(ContainerBackend.CONTAINER_KEY_STATUS) == SuspendableContainerBackend.CONTAINER_STATUS_SUSPENDED

    def container_snapshot_exists(self, snapshot, **kwargs):
        """
        :inherit.
        """
        snapshots = self.get_container_snapshots()
        return next((sh for sh in snapshots if snapshot == sh.get(ContainerBackend.KEY_PK)), False) is not False

    def create_container(self, name, ports, volumes, cmd=None, image=None, clone_of=None, **kwargs):
        """
        :inherit.
        """
        specification = {
            'name': name,
            'ports': ports,
            'volumes': volumes,
            'cmd': cmd,
            'image': image,
            'clone_of': clone_of
        }
        specification.update(kwargs)
        response = None
        try:
            response = requests.post(
                url=self.url + self.slugs.get('containers'),
                data=json.dumps(specification)
            )
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.created:
            return response.json()
        else:
            raise ContainerBackendError

    def create_container_image(self, container, name, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.post(
                url=self.url + self.slugs.get('images'),
                data=json.dumps({
                    'container': container,
                    'name': name
                })
            )
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.created:
            return response.json()
        elif response.status_code == requests.codes.not_found:
            raise ContainerNotFoundError
        else:
            raise ContainerBackendError

    def create_container_snapshot(self, container, name, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.post(
                url=self.generate_container_snapshots_url(container),
                data=json.dumps({
                    'name': name
                })
            )
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.created:
            return response.json()
        elif response.status_code == requests.codes.not_found:
            raise ContainerNotFoundError
        else:
            raise ContainerBackendError

    def delete_container(self, container, force=False, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.delete(url=self.generate_container_url(container))
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.no_content:
            return True
        elif response.status_code == requests.codes.not_found:
            raise ContainerNotFoundError
        else:
            raise ContainerBackendError

    def delete_container_image(self, image, force=False, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.delete(url=self.generate_image_url(image))
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.no_content:
            return True
        elif response.status_code == requests.codes.not_found:
            raise ContainerImageNotFoundError
        else:
            raise ContainerBackendError

    def delete_container_snapshot(self, snapshot, force=False, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.delete(url=self.generate_snapshot_url(snapshot))
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.no_content:
            return True
        elif response.status_code == requests.codes.not_found:
            raise ContainerSnapshotNotFoundError
        else:
            raise ContainerBackendError

    def exec_in_container(self, container, cmd, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.post(
                url=self.generate_container_url(container) + '/exec',
                data=json.dumps({
                    'command': cmd
                })
            )
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.ok:
            return response.json()
        elif response.status_code == requests.codes.not_found:
            raise ContainerNotFoundError
        elif response.status_code == requests.codes.precondition_required:
            raise IllegalContainerStateError
        else:
            raise ContainerBackendError

    def generate_container_url(self, container):
        """
        Generate the full URL with which the container resource can be accessed on the remote API.

        :param container: The container identifier to generate the URL for.
        """
        return self.url + self.slugs.get('containers') + '/' + container

    def generate_container_snapshots_url(self, container):
        """
        Generate the full URL with which the container's snapshot resource can be accessed on the remote API.

        :param container: The container identifier to generate the snapshot URL for.
        """
        return self.url + self.slugs.get('container_snapshots').replace(HttpRemote.PLACEHOLDER_CONTAINER, container)

    def generate_image_url(self, image):
        """
        Generate the full URL with which the image resource can be accessed on the remote API.

        :param image: The image identifier to generate the URL for.
        """
        return self.url + self.slugs.get('images') + '/' + image

    def generate_snapshot_url(self, snapshot):
        """
        Generate the full URL with which the snapshot resource can be accessed on the remote API.

        :param snapshot: The snapshot identifier to generate the URL for.
        """
        return self.url + self.slugs.get('snapshots') + '/' + snapshot

    def get_container(self, container, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.get(url=self.generate_container_url(container))
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.ok:
            return response.json()
        elif response.status_code == requests.codes.not_found:
            raise ContainerNotFoundError
        else:
            raise ContainerBackendError

    def get_container_image(self, image, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.get(url=self.generate_image_url(image))
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.ok:
            return response.json()
        elif response.status_code == requests.codes.not_found:
            raise ContainerImageNotFoundError
        else:
            raise ContainerBackendError

    def get_container_images(self, image, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.get(url=self.url + self.slugs.get('images'))
        except RequestException as ex:
            raise ConnectionError(ex)
        except Excpetion as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.ok:
            return response.json()
        else:
            raise ContainerBackendError

    def get_container_logs(self, container, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.get(url=self.generate_container_url(container) + '/logs')
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.ok:
            return response.json()
        else:
            raise ContainerBackendError

    def get_container_snapshot(self, snapshot, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.get(url=self.generate_snapshot_url(snapshot))
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.ok:
            return response.json()
        elif response.status_code == requests.codes.not_found:
            raise ContainerSnapshotNotFoundError
        else:
            raise ContainerBackendError

    def get_container_snapshots(self, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.get(url=self.url + self.slugs.get('snapshots'))
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.ok:
            return response.json()
        else:
            raise ContainerBackendError

    def get_containers_snapshots(self, container, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.get(url=self.generate_container_snapshots_url(container))
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.ok:
            return response.json()
        elif response.status_code == requests.codes.not_found:
            raise ContainerNotFoundError
        else:
            raise ContainerBackendError

    def get_containers(self, only_running=False, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.get(url=self.url + self.slugs.get('containers'))
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.ok:
            return response.json()
        else:
            raise ContainerBackendError

    def get_status(self):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.get(url=self.url + '/health')
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.ok:
            return response.json().get('backends').get('container').get('status')
        else:
            raise ContainerBackendError

    def restart_container(self, container, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.post(
                url=self.generate_container_url(container) + '/restart',
                data=json.dumps({})
            )
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.no_content:
            return True
        elif response.status_code == requests.codes.not_found:
            raise ContainerNotFoundError
        elif response.status_code == requests.codes.precondition_required:
            raise IllegalContainerStateError
        else:
            raise ContainerBackendError

    def restore_container_snapshot(self, container, snapshot, **kwargs):
        """
        :inherit.
        """
        raise NotImplementedError

    def resume_container(self, container, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.post(
                url=self.generate_container_url(container) + '/resume',
                data=json.dumps({})
            )
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.no_content:
            return True
        elif response.status_code == requests.codes.not_found:
            raise ContainerNotFoundError
        elif response.status_code == requests.codes.precondition_required:
            raise IllegalContainerStateError
        else:
            raise ContainerBackendError

    def start_container(self, container):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.post(
                url=self.generate_container_url(container) + '/start',
                data=json.dumps({})
            )
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.no_content:
            return True
        elif response.status_code == requests.codes.not_found:
            raise ContainerNotFoundError
        elif response.status_code == requests.codes.precondition_required:
            raise IllegalContainerStateError
        else:
            raise ContainerBackendError

    def stop_container(self, container, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.post(
                url=self.generate_container_url(container) + '/stop',
                data=json.dumps({})
            )
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.no_content:
            return True
        elif response.status_code == requests.codes.not_found:
            raise ContainerNotFoundError
        elif response.status_code == requests.codes.precondition_required:
            raise IllegalContainerStateError
        else:
            raise ContainerBackendError

    def suspend_container(self, container, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.post(
                url=self.generate_container_url(container) + '/suspend',
                data=json.dumps({})
            )
        except RequestException as ex:
            raise ConnectionError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

        if response.status_code == requests.codes.no_content:
            return True
        elif response.status_code == requests.codes.not_found:
            raise ContainerNotFoundError
        elif response.status_code == requests.codes.precondition_required:
            raise IllegalContainerStateError
        else:
            raise ContainerBackendError
