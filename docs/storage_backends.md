# Storage Backends

> Official `ipynbsrv.contract.backends.StorageBackend` implementations from the core developers.

## LocalFileSystem

Like its name states, the `LocalFileSystem` storage backend uses the local filesystem to work on. This is probablly the most simple backend that can be used (and currently the only one).

If you want to make use of this implementation, make sure to mount a dedicated directory inside the `ipynbsrv` main container upon creating it:

```bash
docker run ... -v /srv/ipynbsrv/data:/srv/ipynbsrv/data ...
```

> The `homes`, `public` and `shares` directories need to exist inside that directory.

### Setting up SSHFS for remote FS support

Mounting the host directory inside the container as described above is enough to get started for a single-server setup. If you'd like to deploy a multi-server setup you need to ensure the `/srv/ipynbsrv/data` directory is synchronized across all nodes.

A simple solution for that be to use `sshfs`. It can mount remote directories over the SSH protocol (which is encrypted and secure). To get started, install the binary:

```bash
apt-get -y install sshfs
```

Before the remote directory can be mounted, each node should generate an RSA keypair that will later on be used for authentication:

```bash
ssh-keygen -C "ipynbsrv LocalFileSystem SSHFS key" -f ipynbsrv_sshfs -b 1024
```

> Make sure to NOT set a passphrase. You can also choose to generate larger keys, but it might result in bad storage performance.

Finally the public key of each node must be trusted by the master node (or which ever node stores the source directory). For that, copy the content of `/root/.ssh/ipynbsrv_sshfs.pub` to `/root/.ssh/authorized_keys` on that node.

Finally, the remote directory can be mounted:

```bash
sshfs -C -o reconnect,cache_timeout=3,nomap=ignore,allow_other root@192.168.0.1:/srv/ipynbsrv/data/ /srv/ipynbsrv/data/
```

> `192.168.0.1` is the internal only IPv4 address of the node the directory actually resists on (usually the master).    
> –––    
> The command is best placed in `/etc/rc.local` so it is executed on boot.