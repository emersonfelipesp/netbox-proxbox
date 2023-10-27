from enum import Enum

class ProxmoxModeOptions(str, Enum):
    single = "single"
    multi = "multi"
    
class ProxmoxUpperPaths(str, Enum):
    access = "access"
    cluster = "cluster"
    nodes = "nodes"
    storage = "storage"
    version = "version"

class ProxmoxAccessPaths(str, Enum):
    domains = "domains"
    groups = "groups"
    openid = "openid"
    roles = "roles"
    tfa = "tfa"
    users = "users"
    acl = "acl"
    password = "password"
    permissions = "permissions"
    ticket = "ticket"

class ProxmoxClusterPaths(str, Enum):
    acme = "acme"
    backup = "backup"
    backup_info = "backup-info"
    ceph = "ceph"
    config = "config"
    firewall = "firewall"
    ha = "ha"
    jobs = "jobs"
    mapping = "mapping"
    metrics = "metrics"
    replication = "replication"
    sdn = "sdn"
    log = "log"
    nextid = "nextid"
    options = "options"
    resources = "resources"
    status = "status"
    tasks = "tasks"

class ClusterResourcesType(str, Enum):
    vm = "vm"
    storage = "storage"
    node = "node"
    sdn = "sdn"


class ClusterResourcesTypeResponse(str, Enum):
    node = "node"
    storage = "storage"
    pool = "pool"
    qemu = "qemu"
    lxc = "lxc"
    openvz = "openvz"
    sdn = "sdn"
    

class ProxmoxNodesPaths(str, Enum):
    node = "node"

class ResourceType(Enum):
    node = "node"
    storage = "storage"
    pool = "pool"
    qemu = "qemu"
    lxc = "lxc"
    openvz = "openvz"
    sdn = "sdn"
    
class NodeStatus(Enum):
    unknown = "unknown"
    online = "online"
    offline = "offline"