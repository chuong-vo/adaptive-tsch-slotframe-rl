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
 * \addtogroup routing
 * @{
 *
 * @file sdn-routing.c
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#include "net/routing/routing.h"
#include "net/sdn-net/sdn-ds-route.h"

/* Log configuration */
#define DEBUG 0
#if DEBUG
#include <stdio.h>
#define PRINTF(...) printf(__VA_ARGS__)
#else
#define PRINTF(...)
#endif
/*---------------------------------------------------------------------------*/
static void
init(void)
{
    PRINTF("init routing\n");
}
static void
neighbor_state_changed(sdn_ds_nbr_t *nbr)
{
    PRINTF("Neighbor state change\n");
}
static void
neighbor_removed(sdn_ds_nbr_t *nbr)
{
    PRINTF("Neighbor about to remove\n");
    /* Clean routes to this neighbor */
    sdn_ds_route_rm_by_nexthop(&nbr->addr);
    // /* remove route to controller */
    // r = sdn_ds_route_lookup(&ctrl_addr);
    // if (r != NULL)
    //     sdn_ds_route_rm_by_nexthop(&my_rank.addr);
    // // sdn_ds_route_rm(r);
}
static const linkaddr_t *
nexthop(const linkaddr_t *dest)
{
    PRINTF("Looking up for route to %d.%d\n",
           dest->u8[0], dest->u8[1]);
    sdn_ds_route_t *r;
    r = sdn_ds_route_lookup(dest);
    if (r != NULL)
        return sdn_ds_route_nexthop(r);
    /* check if it is one of our neighbors */
    sdn_ds_nbr_t *nbr;
    nbr = sdn_ds_nbr_lookup(dest);
    if (nbr != NULL)
        return &nbr->addr;
    PRINTF("No route found\n");
    return NULL;
}
/*---------------------------------------------------------------------------*/
static uint8_t
is_in_leaf_mode(void)
{
    return 0;
}
/*---------------------------------------------------------------------------*/
const struct routing_driver sdn_routing_driver = {
    "SDN-routing",
    init,
    neighbor_state_changed,
    neighbor_removed,
    nexthop,
    is_in_leaf_mode,
};
/*---------------------------------------------------------------------------*/

/** @}*/
