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
 * @file sdn-ds-route.h
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief Header file for routing table manipulation
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#ifndef SDN_DS_ROUTE_H_
#define SDN_DS_ROUTE_H_

#include "net/nbr-table.h"
#include "sys/stimer.h"
#include "lib/list.h"

#ifdef SDN_CONF_MAX_ROUTES

#define SDN_MAX_ROUTES SDN_CONF_MAX_ROUTES

#else /* UIP_CONF_MAX_ROUTES */

#endif /* UIP_CONF_MAX_ROUTES */

enum
{
    SDN_NODE,
    CONTROLLER,
};

extern uint8_t cluster_head; // Variable used for CH protocol, to know whether we are cluster heads or not.

NBR_TABLE_DECLARE(nbr_routes);

void sdn_ds_route_init(void);

/* Routing table */
#ifdef SDN_MAX_ROUTES
#define SDN_DS6_ROUTE_NB SDN_MAX_ROUTES
#else /* UIP_MAX_ROUTES */
#define SDN_DS6_ROUTE_NB 4
#endif /* UIP_MAX_ROUTES */

/** \brief The neighbor routes hold a list of routing table entries
    that are attached to a specific neihbor. */
struct sdn_ds_route_neighbor_routes
{
    LIST_STRUCT(route_list);
};

/** \brief An entry in the routing table */
typedef struct sdn_ds_route
{
    struct sdn_ds_route *next;
    /* Each route entry belongs to a specific neighbor. That neighbor
     holds a list of all routing entries that go through it. The
     routes field point to the uip_ds6_route_neighbor_routes that
     belong to the neighbor table entry that this routing table entry
     uses. */
    struct sdn_ds_route_neighbor_routes *neighbor_routes;
    linkaddr_t addr;
    int16_t cost;
    uint8_t user; // Flag used to identified if ctrl set this route
} sdn_ds_route_t;

/** \brief A neighbor route list entry, used on the
    uip_ds6_route->neighbor_routes->route_list list. */
struct sdn_ds_route_neighbor_route
{
    struct sdn_ds_route_neighbor_route *next;
    struct sdn_ds_route *route;
};

/** \brief An entry in the default router list */
typedef struct sdn_ds_defrt
{
    struct sdn_ds_defrt *next;
    linkaddr_t addr;
    struct stimer lifetime;
    uint8_t isinfinite;
} sdn_ds_defrt_t;

/** \name Default router list basic routines */
/** @{ */
sdn_ds_defrt_t *sdn_ds_defrt_head(void);
sdn_ds_defrt_t *sdn_ds_defrt_add(const linkaddr_t *addr,
                                 unsigned long interval);
void sdn_ds_defrt_rm(sdn_ds_defrt_t *defrt);
sdn_ds_defrt_t *sdn_ds_defrt_lookup(const linkaddr_t *addr);
const linkaddr_t *sdn_ds_defrt_choose(void);

void sdn_ds_defrt_periodic(void);
/** @} */

/** \name Routing Table basic routines */
/** @{ */
sdn_ds_route_t *sdn_ds_route_lookup(const linkaddr_t *destaddr);
sdn_ds_route_t *sdn_ds_route_add(const linkaddr_t *dest, int16_t cost,
                                 const linkaddr_t *next_hop,
                                 uint8_t user);
void sdn_ds_route_rm(sdn_ds_route_t *route);
void sdn_ds_route_rm_by_nexthop(const linkaddr_t *nexthop);

const linkaddr_t *sdn_ds_route_nexthop(sdn_ds_route_t *);
int sdn_ds_route_num_routes(void);
sdn_ds_route_t *sdn_ds_route_head(void);
sdn_ds_route_t *sdn_ds_route_next(sdn_ds_route_t *);
int sdn_ds_route_is_nexthop(const linkaddr_t *addr);

#endif

/** @} */

/** @} */