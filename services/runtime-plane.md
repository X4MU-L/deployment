# Runtime Plane (Runner Nodes)

The runtime plane is the future home for containerized applications.

It remains part of the long-term architecture, but it is **not** part of the first sellable static deploy product.

## Responsibilities (later milestone)

- receive desired deploy state
- pull container images
- start and stop containers
- run health checks
- report status changes
- ship runtime logs

## Why It Is Deferred

Container runtime support introduces concerns that the static product does not need:

- image distribution
- health-checked rollout
- node placement and capacity
- stable origin routing to runner nodes

Deferring it keeps the first milestone small enough to ship and validate.

## Expected Alpha Shape

- one or a few VPS nodes
- a runner agent on each node
- start new container, pass health check, switch route, stop old container

## Security Notes

- treat user containers as untrusted
- do not colocate runner nodes with control-plane data stores
- use service-scoped auth between runner and control plane

## Relationship To Routing

When the runtime plane is added:

- the Worker stays the public front door
- the Worker forwards container traffic to a stable origin router
- the origin router forwards to the right runner node

The Worker should not need direct knowledge of every runtime node.
