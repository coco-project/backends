# Container Backends

> Official `ipynbsrv.contract.backends.ContainerBackend` implementations from the core developers.

## Docker

Using the `Docker` backend, one can use an existing Docker server for deploying (user) created containers. The implemenation is based on the official `docker-py` package and communicates with the Docker daemon over its Unix socket. The only requirement is therefor access to that socket and enough permissions to read to/write from it.

This backend is perfectly suited for single-server deployments. Make sure to mount the Docker Unix socket within the main container in that case:

```bash
docker run ... -v /var/run/docker.sock:/var/run/docker.sock ...
```

### Configuring the Docker daemon

Some adjustments should be made to the default Docker configuration for best security. They are however optional.

Edit `/etc/default/docker` and append additional options to the `DOCKER_OPTS` variable so it looks something like:

```bash
DOCKER_OPTS="... --icc=false --iptables=true --ip-forward=true ..."
```

> If you're using `Open vSwitch` for the internal multi-server network, `--mtu=1420` must be added as well.

Make sure to restart the Docker daemon afterwards:

```bash
service docker stop && service docker start
```

To enable support for resource limiting (memory and swap) edit `/etc/default/grub` and add:

```bash
GRUB_CMDLINE_LINUX="... cgroup_enable=memory swapaccount=1 ..."
```

Finish by rebooting the system:

```bash
update-grub && reboot
```

### Deploying the Docker Registry

If you want to benefit from the multi-server support built into `ipynbsrv`, you need to ensure that the (internally created) container images are available on all nodes, since the `ServerSelectionAlgorithm` in use might pick a random server to deploy a container.
One way to accomplish that is using the official Docker Registry as a centralized image store. The documentation can be found here: [https://www.docker.com/docker-registry](https://www.docker.com/docker-registry).

The next few chapters summarize the steps required.

#### Running the Registry container

```bash
docker run -d --name registry \
  --restart=always \
  -p 192.168.0.1:5000:5000 \
  -e REGISTRY_STORAGE_MAINTENANCE_UPLOADPURGING_ENABLED=false \
  registry:2
```

> `192.168.0.1` should be the internal only IPv4 address of the node the container runs on (usually the master).

#### Configuring the Docker daemon

Because the simpliest deployment process is used for the registry, we have to explicity tell the Docker daemon on each node to trust our registry:

Edit `/etc/default/docker` and append `--insecure-registry` to the `DOCKER_OPTS` variable so it looks something like:

```bash
DOCKER_OPTS="... --insecure-registry 192.168.0.1:5000 ..."
```

> `192.168.0.1` should be the internal only IPv4 address of the node the container runs on (usually the master).

Make sure to restart the Docker daemon afterwards:

```bash
service docker stop && service docker start
```

#### Telling the backend about the Registry

Do make use of the registry, you finally have to tell the backend that one is in use. Usually you'll be using the `HttpRemote` backend as a proxy before the actual Docker backend. In this case, you'd have to initialize/run it with:

```bash
ipynbsrv_hostapi ... --container-backend='ipynbsrv.backends.container_backends.Docker' --container-backend-args='{"registry": "192.168.0.1:5000"}' ...
```

### Building the container images

Docker containers are bootstrapped from images. The images themselves are created from `Dockerfile`s. You can read more about them here: [http://docs.docker.com/reference/builder/](http://docs.docker.com/reference/builder/).

To make it easy for you, the Docker container backend ships with its own `Dockerfile` that is highly optimized for the use with `ipynbsrv`. It takes care of port mappings, mount points (volumes) and access control, which will limit access to the owner of the container.

To get started, get the files from [https://git.rackster.ch/ipynbsrv/dockerfiles/tree/master/base-ldap](https://git.rackster.ch/ipynbsrv/dockerfiles/tree/master/base-ldap) (or even better, clone the whole repository) and `cd` into the `base-ldap` directory. To build the image, issue:

```bash
docker build -t ipynbsrv/base-ldap:latest .
```

#### Pushing the image to the Registry

Building the image as described above is enough if you are deploying a single-server setup. If you are however deploying multiple servers, make sure the image is available on all nodes. This can be archived by tagging and pushing the newly build image to our private registry:

```
docker tag ipynbsrv/base-ldap:latest 192.168.0.1:5000/ipynbsrv/base-ldap:latest
docker push 192.168.0.1:5000/ipynbsrv/base-ldap:latest
```

> `192.168.0.1` is the internal only IPv4 address of the node the registry is run on (usually the master node).

#### Adding the images to the application

Last but not least, you have to add the images to the application's database. For that, login to the admin interface and go to **Core -> Container Images**.

You can pick what ever name you want, a meaningful description and an owner.

> If it's a system-wide public image, it is best to choose a superadmin as owner.

The important fields are the **Backend Properties**. Fill them as follow:

- **Backend PK:** The primary key identifying this image. For `Docker` this is something like `192.168.0.1:5000/ipynbsrv/ipython2-notebook:latest`. Run `docker images` to get that identifier.
- **Command:** The command to run is specified by the image in use. Consult the image's `Dockerfile` to find it.
- **Protected Port:** Again, this depends on the image. Check out the image's `Dockerfile`.
- **Public Ports:** Same game again.

After saving the image, containers can be created from it.

## HttpRemote

The `HttpRemote` is a proxy backend to other container backend implementations supporting an HTTP interface. It's perfectly suitable for remote nodes, where the local backend is exposed via an HTTP API. The default multi-server implementation is build around this behavior.

### Using the default HTTP API implementation

The `HttpRemote` backend is pre-configured to work flawlessly with the `ipynbsrv.hostapi` package, which provides an HTTP interface to local container backends (e.g. `Docker`). In most cases, this is what you want.

> **Attention:** The resources primary key's are base64 encoded for requests. Make sure to decode on the receiving end!

#### Deploying the HTTP API

First you should install the Python package on the node you want to expose the local container backend:

```bash
pip install ipynbsrv-hostapi
```

Run it afterwards (see the `ipynbsrv.hostapi` documentation for all supported parameters):

```bash
nohup ipynbsrv_hostapi --listen 192.168.0.2 &
```

> `192.168.0.2` is the internal only IPv4 address of the to be exposed node.
> –––
> Consider using a process monitoring tool like `monit` or `supervisord` to make sure the API is accessable all time.