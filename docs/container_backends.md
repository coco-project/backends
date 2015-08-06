# Container Backends

> Official `ipynbsrv.contract.backends.ContainerBackend` implementations from the core developers.

## Docker

Using the `Docker` backend, one can use an existing Docker server for deploying (user) created containers. The implemenation is based on the official `docker-py` package and communicates with the Docker daemon over its Unix socket. The only requirement is therefor access to that socket and enough permissions to read to/write from it.

This backend is perfectly suited for single-server deployments. Make sure to mount the Docker Unix socket within the main container in that case:

```bash
docker run ... -v /var/run/docker.sock:/var/run/docker.sock ...
```

### Configuring the Docker daemon

Some adjustments should be made to the default Docker configuration for best security.

Edit `/etc/default/docker` and append some options to the `DOCKER_OPTS` variable so it looks something like:

```bash
DOCKER_OPTS="... --icc=false --iptables=true --ip-forward=true ..."
```

> If you're using `Open vSwitch` for the internal multi-server network, `--mtu=1420` must be added as well.

Make sure to restart the Docker daemon afterwards:

```bash
service docker stop && service docker start
```

### Deploying the Docker Registery

If you want to benefit from the multi-server support built into `ipynbsrv`, you need to ensure that the (internally created) container images are available on all nodes, since the `ServerSelectionAlgorithm` in use might pick a random server to deploy a container.
One way to accomplish that is using the official Docker Registery as a centralized image store. The documentation can be found here: [https://www.docker.com/docker-registry](https://www.docker.com/docker-registry).

The next few chapters summarize the steps required.

#### Running the Registery container

```bash
docker run -d --name registry \
  --restart=always \
  -p 192.168.0.1:5000:5000 \
  -e REGISTERY_STORAGE_MAINTENANCE_UPLOADPURGING_ENABLED=false \
  registry:2
```

> `192.168.0.1` should be the internal only IPv4 address of the node the container runs on (usually the master).

#### Configuring the Docker daemon

Because the simpliest deployment process is used for the registery, we have to explicity tell the Docker daemon on each node to trust our registery:

Edit `/etc/default/docker` and append `--insecure-registry` to the `DOCKER_OPTS` variable so it looks something like:

```bash
DOCKER_OPTS="... --insecure-registry 192.168.0.1:5000 ..."
```

> `192.168.0.1` should be the internal only IPv4 address of the node the container runs on (usually the master).

Make sure to restart the Docker daemon afterwards:

```bash
service docker stop && service docker start
```

--- TODO: constructor arguments ---

## HttpRemote

The `HttpRemote` is a proxy backend to other container backend implementations supporting an HTTP interface. It's perfectly suitable for remote nodes, where the local backend is exposed via an HTTP API. The default multi-server implementation is build around this behavior.

### Using the default HTTP API implementation

The `HttpRemote` backend is pre-configured to work flawlessly with the `ipynbsrv.hostapi` package, which provides an HTTP interface to local container backends (e.g. `Docker`). In most cases, this is what you want.

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