from base64 import standard_b64encode
from coco.contract.backends import *
from coco.contract.errors import *
from docker import Client, utils as docker_utils
from docker.errors import APIError as DockerError
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
    CONTAINER_NAME_PREFIX = 'coco-'

    """
    The prefix that is prepended to the name of created container snapshots.
    """
    CONTAINER_SNAPSHOT_NAME_PREFIX = 'snapshot-'

    def __init__(self, base_url='unix://var/run/docker.sock', version=None,
                 registry=None
                 ):
        """
        Initialize a new Docker container backend.

        :param base_url: The URL or unix path to the Docker API endpoint.
        :param version: The Docker API version number (see docker version).
        :param registry: If set, created images will be pushed to this registery.
        """
        try:
            self._client = Client(
                base_url=base_url,
                timeout=600,
                version=version
            )
            self._registry = registry
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

    def create_container(self, username, uid, name, ports, volumes,
                         cmd=None, base_url=None, image=None, clone_of=None, **kwargs):
        """
        :inherit.
        """
        name = "%su%i-%s" % (self.CONTAINER_NAME_PREFIX, uid, name)
        if self.container_exists(name):
            raise ContainerBackendError("A container with that name already exists")
        if clone_of is not None and not self.container_exists(clone_of):
            raise ContainerNotFoundError("Base container for the clone does not exist")

        # cloning
        if clone_of:
            # TODO: some way to ensure no regular image is created with that name
            image = self.create_container_image(clone_of, 'for-clone-' + name + '-at-' + str(int(time.time())), push=False)
            image_pk = image.get(ContainerBackend.KEY_PK)
        else:
            image_pk = image
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
                port.get(ContainerBackend.PORT_MAPPING_KEY_EXTERNAL)
            )

        container = None
        try:
            if self._registry and not clone_of:
                parts = image_pk.split('/')
                if len(parts) > 2:  # includes registry
                    repository = parts[0] + '/' + parts[1] + '/' + parts[2].split(':')[0]
                    tag = parts[2].split(':')[1]
                else:
                    repository = image_pk.split(':')[0]
                    tag = image_pk.split(':')[1]
                # FIXME: should be done automatically
                self._client.pull(
                    repository=repository,
                    tag=tag
                )

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
                environment={
                    'OWNER': username,
                    'BASE_URL': base_url
                },
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
        full_image_name = self.get_internal_container_image_name(container, name)
        if self.container_image_exists(full_image_name):
            raise ContainerBackendError("An image with that name already exists for the given container")

        if self._registry:
            parts = full_image_name.split('/')
            registry = parts[0]
            repository = parts[1] + '/' + parts[2].split(':')[0]
            tag = parts[2].split(':')[1]
            commit_name = registry + '/' + repository
        else:
            repository = full_image_name.split(':')[0]
            tag = full_image_name.split(':')[1]
            commit_name = repository

        try:
            self._client.commit(
                container=container,
                repository=commit_name,
                tag=tag
            )
            if self._registry and kwargs.get('push', True):
                self._client.push(
                    repository=full_image_name,
                    stream=False,
                    insecure_registry=True  # TODO: constructor?
                )
            return {
                ContainerBackend.KEY_PK: full_image_name
            }
        except Exception as ex:
            print ex
            raise ContainerBackendError(ex)

    def create_container_snapshot(self, container, name, **kwargs):
        """
        :inherit.
        """
        return self.create_container_image(container, self.CONTAINER_SNAPSHOT_NAME_PREFIX + name, push=False)

    def delete_container(self, container, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        try:
            if self.container_is_suspended(container):
                self.resume_container(container)
            if self.container_is_running(container):
                self.stop_container(container)
        except:
            pass

        try:
            return self._client.remove_container(container=container, force=True)
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerNotFoundError
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def delete_container_image(self, image, **kwargs):
        """
        :inherit.
        """
        if not self.container_image_exists(image):
            raise ContainerImageNotFoundError

        try:
            self._client.remove_image(image=image, force=True)
        except DockerError as ex:
            if ex.response.status_code == requests.codes.not_found:
                raise ContainerImageNotFoundError
            raise ContainerBackendError(ex)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def delete_container_snapshot(self, snapshot, **kwargs):
        """
        :inherit.
        """
        try:
            self.delete_container_image(snapshot, **kwargs)
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
            self._client.inspect_image(image)
            return {
                ContainerBackend.KEY_PK: image
            }
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
                    images.append({
                        ContainerBackend.KEY_PK: image.get('RepoTags')[0]
                    })
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
            container_name = re.sub(
                # i.e. coco-u2500-ipython
                r'^/' + self.CONTAINER_NAME_PREFIX + r'u(\d+)-(.+)$',
                # i.e. coco-u2500/ipython:shared-name
                self.CONTAINER_NAME_PREFIX + r'u\g<1>' + '/' + r'\g<2>' + ':' + name,
                container_name
            )
            if self._registry:
                container_name = self._registry + '/' + container_name
            return container_name
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
            ContainerBackend.CONTAINER_KEY_STATUS: status
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
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError

        try:
            return self._client.restart(container=container, timeout=0)
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
        if not self.container_snapshot_exists(snapshot):
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
        # if self.container_is_running(container):
        #     raise IllegalContainerStateError

        try:
            return self._client.start(container=container, **kwargs)
        except Exception as ex:
            raise ContainerBackendError(ex)

    def stop_container(self, container, **kwargs):
        """
        :inherit.
        """
        if not self.container_exists(container):
            raise ContainerNotFoundError
        # if not self.container_is_running(container):
        #     raise IllegalContainerStateError

        try:
            self.resume_container(container)
        except:
            pass

        try:
            return self._client.stop(container=container, timeout=0)
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
        if not self.container_is_running(container):  # or self.container_is_suspended(container):
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
        return container.get(ContainerBackend.CONTAINER_KEY_STATUS) == ContainerBackend.CONTAINER_STATUS_RUNNING \
            or container.get(ContainerBackend.CONTAINER_KEY_STATUS) == SuspendableContainerBackend.CONTAINER_STATUS_SUSPENDED

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

    def create_container(self, username, uid, name, ports, volumes,
                         cmd=None, base_url=None, image=None, clone_of=None, **kwargs):
        """
        :inherit.
        """
        specification = {
            'username': username,
            'uid': uid,
            'name': name,
            'ports': ports,
            'volumes': volumes,
            'cmd': cmd,
            'base_url': base_url,
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

    def delete_container(self, container, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.delete(
                url=self.generate_container_url(container),
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
        else:
            raise ContainerBackendError

    def delete_container_image(self, image, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.delete(
                url=self.generate_image_url(image),
                data=json.dumps({})
            )
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

    def delete_container_snapshot(self, snapshot, **kwargs):
        """
        :inherit.
        """
        response = None
        try:
            response = requests.delete(
                url=self.generate_snapshot_url(snapshot),
                data=json.dumps({})
            )
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
        return self.url + self.slugs.get('containers') + '/' + standard_b64encode(container)

    def generate_container_snapshots_url(self, container):
        """
        Generate the full URL with which the container's snapshot resource can be accessed on the remote API.

        :param container: The container identifier to generate the snapshot URL for.
        """
        return self.url + self.slugs.get('container_snapshots') \
                                    .replace(HttpRemote.PLACEHOLDER_CONTAINER, standard_b64encode(container))

    def generate_image_url(self, image):
        """
        Generate the full URL with which the image resource can be accessed on the remote API.

        :param image: The image identifier to generate the URL for.
        """
        return self.url + self.slugs.get('images') + '/' + standard_b64encode(image)

    def generate_snapshot_url(self, snapshot):
        """
        Generate the full URL with which the snapshot resource can be accessed on the remote API.

        :param snapshot: The snapshot identifier to generate the URL for.
        """
        return self.url + self.slugs.get('snapshots') + '/' + standard_b64encode(snapshot)

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
