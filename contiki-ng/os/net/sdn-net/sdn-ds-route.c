/*
 * Copyright (c) 2022, Technical University of Denmark.
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 *
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 * 3. Neither the name of the copyright holder nor the names of its
 *    contributors may be used to endorse or promote products derived
 *    from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 * FOR A PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE
 * COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
 * (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 * HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
 * STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
 * OF THE POSSIBILITY OF SUCH DAMAGE.
 *
 */

/**
 * \addtogroup sdn-ds-route
 * @{
 *
 * @file sdn-ds-route.c
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief routing table manipulation
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#include "net/ipv6/uip-ds6.h"
#include "sdn-ds-nbr.h"
#include "sdn-ds-route.h"

#include "lib/list.h"
#include "lib/memb.h"
#include "net/nbr-table.h"

#if BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED || BUILD_WITH_SDN_ORCHESTRA
#include "sdn.h"
#include "net/mac/tsch/tsch.h"
#endif /* BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED || BUILD_WITH_SDN_ORCHESTRA */

/* Log configuration */
#include "sys/log.h"
#define LOG_MODULE "ROUTE-DS"
#if LOG_CONF_LEVEL_ROUTE_DS
#define LOG_LEVEL LOG_CONF_LEVEL_ROUTE_DS
#else
#define LOG_LEVEL LOG_LEVEL_NONE
#endif /* LOG_CONF_LEVEL_ROUTE_DS */

uint8_t cluster_head;

#if (SDN_MAX_ROUTES != 0)
/* The nbr_routes holds a neighbor table to be able to maintain
   information about what routes go through what neighbor. This
   neighbor table is registered with the central nbr-table repository
   so that it will be maintained along with the rest of the neighbor
   tables in the system. */
NBR_TABLE_GLOBAL(struct sdn_ds_route_neighbor_routes, nbr_routes);
MEMB(neighborroutememb, struct sdn_ds_route_neighbor_routes, SDN_DS6_ROUTE_NB);

/* Each route is repressented by a uip_ds6_route_t structure and
   memory for each route is allocated from the routememb memory
   block. These routes are maintained on the routelist. */
LIST(routelist);
MEMB(routememb, sdn_ds_route_t, SDN_DS6_ROUTE_NB);

static int num_routes = 0;
static void rm_routelist_callback(nbr_table_item_t *ptr);

#endif /* (SDN_MAX_ROUTES != 0) */

#if DEBUG
static void sdn_ds_route_print(void);
#endif

/* Default routes are held on the defaultrouterlist and their
   structures are allocated from the defaultroutermemb memory block.*/
LIST(defaultrouterlist);
MEMB(defaultroutermemb, sdn_ds_defrt_t, UIP_DS6_DEFRT_NB);

/*---------------------------------------------------------------------------*/
#if (SDN_MAX_ROUTES != 0)
static void
rm_routelist(struct sdn_ds_route_neighbor_routes *routes)
{
    // if (PRINTF_ENABLED)
    // {
    //     assert_nbr_routes_list_sane();
    // }

    if (routes != NULL && routes->route_list != NULL)
    {
        struct sdn_ds_route_neighbor_route *r;
        r = list_head(routes->route_list);
        while (r != NULL)
        {
            sdn_ds_route_rm(r->route);
            r = list_head(routes->route_list);
        }
        nbr_table_remove(nbr_routes, routes);
    }

    // if (PRINTF_ENABLED)
    // {
    //     assert_nbr_routes_list_sane();
    // }
}
/*---------------------------------------------------------------------------*/
static void
rm_routelist_callback(nbr_table_item_t *ptr)
{
    rm_routelist((struct sdn_ds_route_neighbor_routes *)ptr);
}
#endif /* (SDN_MAX_ROUTES != 0) */
/*---------------------------------------------------------------------------*/
void sdn_ds_route_init(void)
{
    cluster_head = 0; // We set the node to non-CH.
#if (SDN_MAX_ROUTES != 0)
    memb_init(&routememb);
    list_init(routelist);
    nbr_table_register(nbr_routes,
                       (nbr_table_callback *)rm_routelist_callback);
#endif /* (SDN_MAX_ROUTES != 0) */

    memb_init(&defaultroutermemb);
    list_init(defaultrouterlist);
}
/*---------------------------------------------------------------------------*/
#if (SDN_MAX_ROUTES != 0)
static linkaddr_t *
sdn_ds_route_nexthop_lladdr(sdn_ds_route_t *route)
{
    if (route != NULL)
    {
        return (linkaddr_t *)nbr_table_get_lladdr(nbr_routes,
                                                  route->neighbor_routes);
    }
    else
    {
        return NULL;
    }
}
#endif /* (SDN_MAX_ROUTES != 0) */
/*---------------------------------------------------------------------------*/
const linkaddr_t *
sdn_ds_route_nexthop(sdn_ds_route_t *route)
{
#if (SDN_MAX_ROUTES != 0)
    if (route != NULL)
    {
        return sdn_ds_route_nexthop_lladdr(route);
    }
    else
    {
        return NULL;
    }
#else  /* (SDN_MAX_ROUTES != 0) */
    return NULL;
#endif /* (SDN_MAX_ROUTES != 0) */
}
/*---------------------------------------------------------------------------*/
sdn_ds_route_t *
sdn_ds_route_head(void)
{
#if (SDN_MAX_ROUTES != 0)
    return list_head(routelist);
#else  /* (SDN_MAX_ROUTES != 0) */
    return NULL;
#endif /* (SDN_MAX_ROUTES != 0) */
}
/*---------------------------------------------------------------------------*/
sdn_ds_route_t *
sdn_ds_route_next(sdn_ds_route_t *r)
{
#if (SDN_MAX_ROUTES != 0)
    if (r != NULL)
    {
        sdn_ds_route_t *n = list_item_next(r);
        return n;
    }
#endif /* (SDN_MAX_ROUTES != 0) */
    return NULL;
}
/*---------------------------------------------------------------------------*/
int sdn_ds_route_is_nexthop(const linkaddr_t *addr)
{
#if (SDN_MAX_ROUTES != 0)

    if (addr == NULL)
    {
        return 0;
    }

    return nbr_table_get_from_lladdr(nbr_routes, (linkaddr_t *)addr) != NULL;
#else  /* (SDN_MAX_ROUTES != 0) */
    return 0;
#endif /* (SDN_MAX_ROUTES != 0) */
}
/*---------------------------------------------------------------------------*/
int sdn_ds_route_num_routes(void)
{
#if (SDN_MAX_ROUTES != 0)
    return num_routes;
#else  /* (SDN_MAX_ROUTES != 0) */
    return 0;
#endif /* (SDN_MAX_ROUTES != 0) */
}
/*---------------------------------------------------------------------------*/
sdn_ds_route_t *
sdn_ds_route_lookup(const linkaddr_t *addr)
{
#if (SDN_MAX_ROUTES != 0)
    sdn_ds_route_t *r;
    sdn_ds_route_t *found_route;
    // uint8_t longestmatch;

    LOG_INFO("Looking up route for %d.%d\n",
             addr->u8[0], addr->u8[1]);

    if (addr == NULL)
    {
        return NULL;
    }

    found_route = NULL;
    // longestmatch = 0;
    for (r = sdn_ds_route_head();
         r != NULL;
         r = sdn_ds_route_next(r))
    {
        if (linkaddr_cmp(addr, &r->addr))
            found_route = r;
        // if(r->length >= longestmatch &&
        //    uip_addr_prefixcmp(addr, &r->addr, r->length)) {
        //   longestmatch = r->length;
        //   found_route = r;
        //   /* check if total match - e.g. all 128 bits do match */
        //   if(longestmatch == 128) {
        // break;
        //   }
        // }
    }

    if (found_route != NULL)
    {
        LOG_INFO("Found route: %d.%d",
                 addr->u8[0], addr->u8[1]);
        LOG_INFO_(" via %d.%d\n",
                  sdn_ds_route_nexthop(found_route)->u8[0], sdn_ds_route_nexthop(found_route)->u8[1]);
    }
    else
    {
        LOG_INFO("No route found\n");
    }

    if (found_route != NULL && found_route != list_head(routelist))
    {
        /* If we found a route, we put it at the start of the routeslist
       list. The list is ordered by how recently we looked them up:
       the least recently used route will be at the end of the
       list - for fast lookups (assuming multiple packets to the same node). */

        list_remove(routelist, found_route);
        list_push(routelist, found_route);
    }

    return found_route;
#else  /* (SDN_MAX_ROUTES != 0) */
    return NULL;
#endif /* (SDN_MAX_ROUTES != 0) */
}
/*---------------------------------------------------------------------------*/
sdn_ds_route_t *
sdn_ds_route_add(const linkaddr_t *dest, int16_t cost,
                 const linkaddr_t *nexthop,
                 uint8_t user)
{
#if (SDN_MAX_ROUTES != 0)
    sdn_ds_route_t *r;
    struct sdn_ds_route_neighbor_route *nbrr;

    // if (PRINTF_ENABLED)
    // {
    //     assert_nbr_routes_list_sane();
    // }

    if (dest == NULL || nexthop == NULL)
    {
        return NULL;
    }

    // #ifdef BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED
    //     if (linkaddr_cmp(dest, &ctrl_addr))
    //     {
    //         PRINTF("destination is ctrl.\n");
    //         if (tsch_is_associated == 1)
    //         {
    //             PRINTF("tsch associated.\n");
    //             tsch_queue_update_time_source(nexthop);
    //         }
    //     }
    // #endif /* BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED */

    /* Get link-layer address of next hop, make sure it is in neighbor table */
    const linkaddr_t *nexthop_lladdr = nexthop;
    if (nexthop_lladdr == NULL)
    {
        LOG_INFO("Add: neighbor link-local address unknown for %d.%d\n",
                 nexthop->u8[0], nexthop->u8[1]);
        return NULL;
    }

    /* First make sure that we don't add a route twice. If we find an
     existing route for our destination, we'll delete the old
     one first. */
    r = sdn_ds_route_lookup(dest);
    if (r != NULL)
    {
        if (r->user == CONTROLLER && user == SDN_NODE)
            return NULL;
        const linkaddr_t *current_nexthop;
        current_nexthop = sdn_ds_route_nexthop(r);
        if (current_nexthop != NULL && linkaddr_cmp(nexthop, current_nexthop))
        {
            /* no need to update route - already correct! */
            return r;
        }
        LOG_INFO("Add: old route for %d.%d",
                 dest->u8[0], dest->u8[1]);
        LOG_INFO_(" found, deleting it\n");

        sdn_ds_route_rm(r);
    }
    {
        struct sdn_ds_route_neighbor_routes *routes;
        /* If there is no routing entry, create one. We first need to
       check if we have room for this route. If not, we remove the
       least recently used one we have. */

        if (sdn_ds_route_num_routes() == SDN_DS6_ROUTE_NB)
        {
            sdn_ds_route_t *oldest;
            oldest = NULL;
#if UIP_DS6_ROUTE_REMOVE_LEAST_RECENTLY_USED
            /* Removing the oldest route entry from the route table. The
         least recently used route is the first route on the list. */
            oldest = list_tail(routelist);
#endif
            if (oldest == NULL)
            {
                return NULL;
            }
            LOG_INFO("Add: dropping route to %d.%d\n",
                     oldest->addr.u8[0], oldest->addr.u8[1]);
            sdn_ds_route_rm(oldest);
        }

        /* Every neighbor on our neighbor table holds a struct
       uip_ds6_route_neighbor_routes which holds a list of routes that
       go through the neighbor. We add our route entry to this list.

       We first check to see if we already have this neighbor in our
       nbr_route table. If so, the neighbor already has a route entry
       list.
    */
        routes = nbr_table_get_from_lladdr(nbr_routes,
                                           (linkaddr_t *)nexthop_lladdr);

        if (routes == NULL)
        {
            /* If the neighbor did not have an entry in our neighbor table,
         we create one. The nbr_table_add_lladdr() function returns a
         pointer to a pointer that we may use for our own purposes. We
         initialize this pointer with the list of routing entries that
         are attached to this neighbor. */
            routes = nbr_table_add_lladdr(nbr_routes,
                                          (linkaddr_t *)nexthop_lladdr,
                                          NBR_TABLE_REASON_ROUTE, NULL);
            if (routes == NULL)
            {
                /* This should not happen, as we explicitly deallocated one
           route table entry above. */
                LOG_WARN("Add: could not allocate neighbor table entry\n");
                return NULL;
            }
            LIST_STRUCT_INIT(routes, route_list);
        }

        /* Allocate a routing entry and populate it. */
        r = memb_alloc(&routememb);

        if (r == NULL)
        {
            /* This should not happen, as we explicitly deallocated one
         route table entry above. */
            LOG_WARN("Add: could not allocate route\n");
            return NULL;
        }

        /* add new routes first - assuming that there is a reason to add this
       and that there is a packet coming soon. */
        list_push(routelist, r);

        nbrr = memb_alloc(&neighborroutememb);
        if (nbrr == NULL)
        {
            /* This should not happen, as we explicitly deallocated one
         route table entry above. */
            LOG_WARN("Add: could not allocate neighbor route list entry\n");
            memb_free(&routememb, r);
            return NULL;
        }

        nbrr->route = r;
        /* Add the route to this neighbor */
        list_add(routes->route_list, nbrr);
        r->neighbor_routes = routes;
        num_routes++;

        LOG_INFO("Add: num %d\n", num_routes);

        /* lock this entry so that nexthop is not removed */
        nbr_table_lock(nbr_routes, routes);
    }

    linkaddr_copy(&(r->addr), dest);
    r->cost = cost;
    r->user = user;

    LOG_INFO("Add: adding route: %d.%d",
             dest->u8[0], dest->u8[1]);
    LOG_INFO_(" via %d.%d\n",
              nexthop->u8[0], nexthop->u8[1]);
// LOG_ANNOTATE("#L %u 1;blue\n", nexthop->u8[sizeof(uip_ipaddr_t) - 1]);

// if (PRINTF_ENABLED)
// {
//     assert_nbr_routes_list_sane();
// }
#if DEBUG
    sdn_ds_route_print();
#endif
    return r;

#else /* (SDN_MAX_ROUTES != 0) */
#if DEBUG
    sdn_ds_route_print();
#endif
    return NULL;
#endif /* (SDN_MAX_ROUTES != 0) */
}
/*---------------------------------------------------------------------------*/
void sdn_ds_route_rm(sdn_ds_route_t *route)
{
#if (SDN_MAX_ROUTES != 0)
    struct sdn_ds_route_neighbor_route *neighbor_route;

    // if (PRINTF_ENABLED)
    // {
    //     assert_nbr_routes_list_sane();
    // }

    if (route != NULL && route->neighbor_routes != NULL)
    {

        LOG_INFO("Rm: removing route: %d.%d\n",
                 route->addr.u8[0], route->addr.u8[1]);

        /* Remove the route from the route list */
        list_remove(routelist, route);

        /* Find the corresponding neighbor_route and remove it. */
        for (neighbor_route = list_head(route->neighbor_routes->route_list);
             neighbor_route != NULL && neighbor_route->route != route;
             neighbor_route = list_item_next(neighbor_route))
            ;

        if (neighbor_route == NULL)
        {
            LOG_INFO("Rm: neighbor_route was NULL for %d.%d\n",
                     route->addr.u8[0], route->addr.u8[1]);
        }
        list_remove(route->neighbor_routes->route_list, neighbor_route);
        if (list_head(route->neighbor_routes->route_list) == NULL)
        {
            /* If this was the only route using this neighbor, remove the
         neighbor from the table - this implicitly unlocks nexthop */
            // #if LOG_WITH_ANNOTATE
            //             uip_ipaddr_t *nexthop = sdn_ds_route_nexthop(route);
            //             if (nexthop != NULL)
            //             {
            //                 LOG_ANNOTATE("#L %u 0\n", nexthop->u8[sizeof(uip_ipaddr_t) - 1]);
            //             }
            // #endif /* LOG_WITH_ANNOTATE */
            LOG_INFO("Rm: removing neighbor too\n");
            nbr_table_remove(nbr_routes, route->neighbor_routes->route_list);
        }
        memb_free(&routememb, route);
        memb_free(&neighborroutememb, neighbor_route);

        num_routes--;

        LOG_INFO("Rm: num %d\n", num_routes);
    }

    // if (PRINTF_ENABLED)
    // {
    //     assert_nbr_routes_list_sane();
    // }

#endif /* (SDN_MAX_ROUTES != 0) */
#if DEBUG
    sdn_ds_route_print();
#endif
    return;
}
/*---------------------------------------------------------------------------*/
void sdn_ds_route_rm_by_nexthop(const linkaddr_t *nexthop)
{
#if (SDN_MAX_ROUTES != 0)
    /* Get routing entry list of this neighbor */
    // const linkaddr_t *nexthop_lladdr;
    struct sdn_ds_route_neighbor_routes *routes;

    // nexthop_lladdr = nexthop;
    routes = nbr_table_get_from_lladdr(nbr_routes,
                                       nexthop);
    rm_routelist(routes);
#endif /* (SDN_MAX_ROUTES != 0) */
}
/*---------------------------------------------------------------------------*/
sdn_ds_defrt_t *sdn_ds_defrt_head(void)
{
    return list_head(defaultrouterlist);
}
/*---------------------------------------------------------------------------*/
sdn_ds_defrt_t *sdn_ds_defrt_add(const linkaddr_t *addr,
                                 unsigned long interval)
{
    sdn_ds_defrt_t *d;

    // if (PRINTF_ENABLED)
    // {
    //     assert_nbr_routes_list_sane();
    // }

    if (addr == NULL)
    {
        return NULL;
    }

    LOG_INFO("Add default\n");
    d = sdn_ds_defrt_lookup(addr);
    if (d == NULL)
    {
        d = memb_alloc(&defaultroutermemb);
        if (d == NULL)
        {
            LOG_INFO("Add default: could not add default route to %d.%d",
                     addr->u8[0], addr->u8[1]);
            LOG_INFO_(", out of memory\n");
            return NULL;
        }
        else
        {
            LOG_INFO("Add default: adding default route to %d.%d\n",
                     addr->u8[0], addr->u8[1]);
        }

        list_push(defaultrouterlist, d);
    }

    linkaddr_copy(&d->addr, addr);
    if (interval != 0)
    {
        stimer_set(&d->lifetime, interval);
        d->isinfinite = 0;
    }
    else
    {
        d->isinfinite = 1;
    }

    // LOG_ANNOTATE("#L %u 1\n", ipaddr->u8[sizeof(uip_ipaddr_t) - 1]);

    // if (PRINTF_ENABLED)
    // {
    //     assert_nbr_routes_list_sane();
    // }

    return d;
}
/*---------------------------------------------------------------------------*/
void sdn_ds_defrt_rm(sdn_ds_defrt_t *defrt)
{
    sdn_ds_defrt_t *d;

    // if (PRINTF_ENABLED)
    // {
    //     assert_nbr_routes_list_sane();
    // }

    /* Make sure that the defrt is in the list before we remove it. */
    for (d = list_head(defaultrouterlist);
         d != NULL;
         d = list_item_next(d))
    {
        if (d == defrt)
        {
            LOG_INFO("Removing default\n");
            list_remove(defaultrouterlist, defrt);
            memb_free(&defaultroutermemb, defrt);
            // LOG_ANNOTATE("#L %u 0\n", defrt->ipaddr.u8[sizeof(uip_ipaddr_t) - 1]);
            return;
        }
    }

    // if (PRINTF_ENABLED)
    // {
    //     assert_nbr_routes_list_sane();
    // }
}
/*---------------------------------------------------------------------------*/
sdn_ds_defrt_t *sdn_ds_defrt_lookup(const linkaddr_t *addr)
{
    sdn_ds_defrt_t *d;
    if (addr == NULL)
    {
        return NULL;
    }
    for (d = list_head(defaultrouterlist);
         d != NULL;
         d = list_item_next(d))
    {
        if (linkaddr_cmp(&d->addr, addr))
        {
            return d;
        }
    }
    return NULL;
}
/*---------------------------------------------------------------------------*/
const linkaddr_t *sdn_ds_defrt_choose(void)
{
    sdn_ds_defrt_t *d;
    sdn_ds_nbr_t *bestnbr;
    linkaddr_t *addr;

    addr = NULL;
    for (d = list_head(defaultrouterlist);
         d != NULL;
         d = list_item_next(d))
    {
        LOG_INFO("Default route, IP address %d.%d\n",
                 d->addr.u8[0], d->addr.u8[1]);
        bestnbr = sdn_ds_nbr_lookup(&d->addr);
        if (bestnbr != NULL /* && bestnbr->state != NBR_INCOMPLETE */)
        {
            LOG_INFO("Default route found, IP address %d.%d\n",
                     d->addr.u8[0], d->addr.u8[1]);
            return &d->addr;
        }
        else
        {
            addr = &d->addr;
            LOG_INFO("Default route Incomplete found, IP address %d.%d\n",
                     d->addr.u8[0], d->addr.u8[1]);
        }
    }
    return addr;
}
/*---------------------------------------------------------------------------*/
void sdn_ds_defrt_periodic(void)
{
    sdn_ds_defrt_t *d;
    d = list_head(defaultrouterlist);
    while (d != NULL)
    {
        if (!d->isinfinite &&
            stimer_expired(&d->lifetime))
        {
            LOG_INFO("Default route periodic: defrt lifetime expired\n");
            sdn_ds_defrt_rm(d);
            d = list_head(defaultrouterlist);
        }
        else
        {
            d = list_item_next(d);
        }
    }
}
/*---------------------------------------------------------------------------*/
#if DEBUG
static void sdn_ds_route_print(void)
{
    LOG_INFO("routing table:\n");
    sdn_ds_route_t *r;
    const linkaddr_t *via;
    // struct sdn_ds_route_neighbor_routes *routes;
    for (r = sdn_ds_route_head();
         r != NULL;
         r = sdn_ds_route_next(r))
    {
        via = sdn_ds_route_nexthop(r);
        LOG_INFO(" dest %d.%d via %d.%d cost %d \n",
                 r->addr.u8[0], r->addr.u8[1],
                 via->u8[0], via->u8[1],
                 r->cost);
        /* PRINTF(" dest ");
            log_lladdr(&r->addr);
            PRINTF(" via ");
            log_lladdr(sdn_ds_route_nexthop(r)); */
    }
    // PRINTF("\n");
}
#endif

/** @} */
/*---------------------------------------------------------------------------*/