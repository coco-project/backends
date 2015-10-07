# Group/User Backends

> Official `coco.contract.backends.GroupBackend` and `coco.contract.backends.UserBackend` implementations from the core developers.

## LdapBackend

The *Lightweight Directory Access Protocol* is a widely supported protocol to communicate with directory servers like Window's Active Directory. The `LdapBackend` implements the `GroupBackend` and `UserBackend` contracts to use such a directory service as a `coco` backend. It can be used to allow users on an existing directory service to login to the application. Under the hood, the `python-ldap` package is used.

This backend is also used for the internally used LDAP server, on which user accounts and groups are stored (so the application doesn't have to rely on the external backend).

### Reusing the internal LDAP server

For the case no external directory service exist, the internal LDAP server can be used to simulate one. This has the benefit that no extra server needs to be setup, because the internal one exists anyway. Only a few additional steps are required compared to the regular setup.

#### Creating the LDAP users unit

The internal LDAP server uses the `groups` and `users` organizational units to store records. To simulate an external source, an additional OU needs to be defined.

This can be done either through a desktop application or the command-line (like in the main install guide).

The easiest way is to enter the internal LDAP container with:

```bash
docker enter coco_ldap
```

> This only works if the core infrastructure is running on Docker (which is the default).

And create a temporary file named `_users.ldif` with the following content:

```
dn: ou=_users,dc=coco,dc=ldap
changetype: add
objectclass: organizationalUnit
objectclass: top
ou: _users
```

Using the LDAP server's administration tools, these instructions can be transfered to the server, which will setup the OU:

```bash
ldapadd -h localhost -p 389 -c -x -D cn=admin,dc=coco,dc=ldap -W -f _users.ldif
```

> You'll be prompted to enter a password. It is the LDAP admin password you defined during the LDAP container bootstrap process.

#### Managing user accounts

You can use whatever LDAP server administration tool you like. If you use `Docker` as your `ContainerBackend`, we recommend you to use [phpLDAPadmin](http://phpldapadmin.sourceforge.net/wiki/index.php/Main_Page), as there is a phpLDAPadmin Docker image available in the official Docker Registry.

Setting up the container only takes one command:

```bash
docker run -d \
  --name coco_phpldapadmin \
  -e HTTPS=false -e LDAP_HOSTS=coco_ldap \
  --link coco_ldap:coco_ldap \
  -p 0.0.0.0:82:80 \
  osixia/phpldapadmin:latest
```

> `LDAP_HOSTS` has to be the address under which the LDAP server can be reached. If you are running the container on the node hosting the LDAP server (usually the master node), you can link the LDAP container and use the defined link name for that.    
> ––––    
> `--link coco_ldap:coco_ldap` links the local container named `coco_ldap` into the container and makes it available as `coco_ldap`.    
> ––––    
> `-p 0.0.0.0:82:80` instructs Docker to expose the service on all interfaces on port 82. You can therefor access it via <server-IP>:82 afterwards.

The login password is the LDAP server's admin password you have set during creation and the "username" is `cn=admin,dc=coco,dc=ldap`.

Now you should have a nice web interface with which you can manage the user accounts within the `_users` organizational unit. When adding a new user, make sure to select *Posix Account* as the structural item.
