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
 * \addtogroup sdn-ds-nbr
 * @{
 *
 * @file sdn-ds-nbr.c
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief Neighbor table - management
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#include "sdn-ds-nbr.h"
#include "net/link-stats.h"
#include "sdn-ds-route.h"
#include "net/routing/routing.h"

/* Log configuration */
#include "sys/log.h"
#define LOG_MODULE "NBR-DS"
#if LOG_CONF_LEVEL_NBR_DS
#define LOG_LEVEL LOG_CONF_LEVEL_NBR_DS
#else
#define LOG_LEVEL LOG_LEVEL_NONE
#endif /* LOG_CONF_LEVEL_NBR_DS */

/* Alpha for moving average */
// #define ALPHA 0.6

#ifndef SDN_CONF_MAX_ND_INTERVAL
#define NEIGHBOR_TIMEOUT 60 * 5 * 3 // Every 5 mins
#else
#define NEIGHBOR_TIMEOUT (SDN_CONF_MAX_ND_INTERVAL * 5)
#endif

#if SDN_DS_NBR_NOTIFICATIONS
LIST(notificationlist);
#endif

NBR_TABLE_GLOBAL(sdn_ds_nbr_t, ds_neighbors);

// static void sdn_ds_nbr_timer_rm(void *n);
static void sdn_ds_nbr_print(void);
// static float exp_mov_avg(float, float);

/*---------------------------------------------------------------------------*/
#if SDN_DS_NBR_NOTIFICATIONS
static void
call_nbr_callback(int event, const sdn_ds_nbr_t *nbr)
{
    struct sdn_ds_nbr_notification *n;
    for (n = list_head(notificationlist);
         n != NULL;
         n = list_item_next(n))
    {
        n->callback(event, nbr);
    }
}
/*---------------------------------------------------------------------------*/
void sdn_ds_nbr_notification_add(struct sdn_ds_nbr_notification *n,
                                 sdn_ds_nbr_notification_callback c)
{
    if (n != NULL && c != NULL)
    {
        n->callback = c;
        list_add(notificationlist, n);
    }
}
/*---------------------------------------------------------------------------*/
void sdn_ds_nbr_notification_rm(struct sdn_ds_nbr_notification *n)
{
    list_remove(notificationlist, n);
}
#endif
/*---------------------------------------------------------------------------*/
void sdn_ds_neighbors_init(void)
{
    link_stats_init();
    nbr_table_register(ds_neighbors, (nbr_table_callback *)sdn_ds_nbr_rm);
}
/*---------------------------------------------------------------------------*/
sdn_ds_nbr_t *
sdn_ds_nbr_add(const linkaddr_t *from, int16_t *ndRank, int16_t *ndRssi,
               int16_t *rcv_rssi, void *data)
{
    sdn_ds_nbr_t *nbr;

    /* Does this NB exists? */
    nbr = sdn_ds_nbr_lookup(from);
    // float exp_avg_old, plus_percent, minus_percent;
    // uint8_t adv = 1;

    if (nbr == NULL)
    {
        /* New NB */
        LOG_INFO("Adding new NB\n");
        nbr = nbr_table_add_lladdr(ds_neighbors, (linkaddr_t *)from, NBR_TABLE_REASON_IPV6_ND, data);
        // adv = 0;
        if (nbr)
        {
            linkaddr_copy(&nbr->addr, from);
            nbr->exp_avg = 0;
            LOG_INFO("Adding neighbor with addr %d.%d\n",
                   from->u8[0], from->u8[1]);
#if SDN_DS_NBR_NOTIFICATIONS
            call_nbr_callback(SDN_DS_NBR_NOTIFICATION_ADD, nbr);
#endif
        }
        else
        {
            LOG_WARN("Add drop addr %d.%d\n",
                   from->u8[0], from->u8[1]);
            return NULL;
        }
    }
    /* Neighbor rssi received from lower layer */
    nbr->rssi = *rcv_rssi;
    /* calculate the exponential average */
    // exp_avg_old = nbr->exp_avg;
    // plus_percent = exp_avg_old + exp_avg_old * 0.05;
    // minus_percent = exp_avg_old - exp_avg_old * 0.05;
    // nbr->exp_avg = exp_mov_avg(nbr->rssi, nbr->exp_avg);
    /* rank to controller */
    nbr->rank = *ndRank;
    /* set the lifetime of node */
    stimer_set(&nbr->lifetime, NEIGHBOR_TIMEOUT);
    // ctimer_set(&nbr->timeout, NEIGHBOR_TIMEOUT, sdn_ds_nbr_timer_rm, nbr);
    /* Print out a message. */
    LOG_INFO("neighbor message received from %d.%d with RSSI %d rank %d cost %d\n", // exp avg %d.%d\n",
           from->u8[0], from->u8[1],
           nbr->rssi,
           nbr->rank,
           nbr->rssi + *ndRssi);
    //    (int)nbr->exp_avg,
    //    (int)(((-1) * nbr->exp_avg - (int)((-1) * nbr->exp_avg)) * 100)); //,
    sdn_ds_nbr_print();
    //     if (nbr->exp_avg < plus_percent || nbr->exp_avg > minus_percent)
    //         adv = 0;
    //     if (!adv)
    //     {
    //         NETSTACK_ROUTING.neighbor_state_changed(nbr);
    //         LOG_INFO("neighbor data changed.\n");
    // #if SDN_DS_NBR_NOTIFICATIONS
    //         call_nbr_callback(SDN_DS_NBR_NOTIFICATION_CH, nbr);
    // #endif
    //     }
    return nbr;
}
/*---------------------------------------------------------------------------*/
// static void sdn_ds_nbr_timer_rm(void *n)
// {
//     sdn_ds_nbr_t *nbr = n;
//     sdn_ds_nbr_rm(nbr);
// }
/*---------------------------------------------------------------------------*/
int sdn_ds_nbr_rm(sdn_ds_nbr_t *nbr)
{
    if (nbr != NULL)
    {
        LOG_WARN("removing neighbor %d.%d\n", nbr->addr.u8[0], nbr->addr.u8[1]);
        NETSTACK_ROUTING.neighbor_removed(nbr);
#if SDN_DS_NBR_NOTIFICATIONS
        call_nbr_callback(SDN_DS_NBR_NOTIFICATION_RM, nbr);
#endif
        return nbr_table_remove(ds_neighbors, nbr);
    }
    return 1;
}
/*---------------------------------------------------------------------------*/
const linkaddr_t *sdn_ds_nbr_get_ll(const sdn_ds_nbr_t *nbr)
{
    return (const linkaddr_t *)nbr_table_get_lladdr(ds_neighbors, nbr);
}
/*---------------------------------------------------------------------------*/
int sdn_ds_nbr_num(void)
{
    int num = 0;

    sdn_ds_nbr_t *nbr;
    for (nbr = nbr_table_head(ds_neighbors);
         nbr != NULL;
         nbr = nbr_table_next(ds_neighbors, nbr))
    {
        num++;
    }
    return num;
}
/*---------------------------------------------------------------------------*/
sdn_ds_nbr_t *sdn_ds_nbr_head(void)
{
    return nbr_table_head(ds_neighbors);
}
/*---------------------------------------------------------------------------*/
sdn_ds_nbr_t *sdn_ds_nbr_next(sdn_ds_nbr_t *nbr)
{
    return nbr_table_next(ds_neighbors, nbr);
}
/*---------------------------------------------------------------------------*/
sdn_ds_nbr_t *sdn_ds_nbr_lookup(const linkaddr_t *addr)
{
    sdn_ds_nbr_t *nbr;
    LOG_INFO("Looking up for neighbor %d.%d\n",
           addr->u8[0], addr->u8[1]);
    if (addr == NULL)
    {
        return NULL;
    }
    for (nbr = sdn_ds_nbr_head(); nbr != NULL; nbr = sdn_ds_nbr_next(nbr))
    {
        if (linkaddr_cmp(&nbr->addr, addr))
        {
            return nbr;
        }
    }
    LOG_INFO("No neighbor found\n");
    return NULL;
}
/*---------------------------------------------------------------------------*/
static void sdn_ds_nbr_print(void)
{
    LOG_INFO("neighbor table:\n");
    sdn_ds_nbr_t *nbr;
    for (nbr = nbr_table_head(ds_neighbors);
         nbr != NULL;
         nbr = nbr_table_next(ds_neighbors, nbr))
    {
        LOG_INFO(" node %d.%d", nbr->addr.u8[0], nbr->addr.u8[1]);
        LOG_INFO_(" exp. rssi avg: %d.%d", (int)nbr->exp_avg,
               (int)(((-1) * nbr->exp_avg - (int)((-1) * nbr->exp_avg)) * 100));
        LOG_INFO_(" rank: %d ( %lus )\n", nbr->rank, stimer_remaining(&nbr->lifetime));
    }
}
/*---------------------------------------------------------------------------*/
void sdn_ds_neighbor_periodic(void)
{
    sdn_ds_nbr_t *nbr;
    nbr = nbr_table_head(ds_neighbors);
    while (nbr != NULL)
    {
        if (stimer_expired(&nbr->lifetime))
        {
            LOG_INFO("sdn_ds_neighbor_periodic: nbr %d.%d",
                   nbr->addr.u8[0], nbr->addr.u8[1]);
            LOG_INFO_(" lifetime expired\n");
            sdn_ds_nbr_rm(nbr);
            nbr = nbr_table_head(ds_neighbors);
        }
        else
        {
            nbr = nbr_table_next(ds_neighbors, nbr);
        }
    }
}

/** @} */
/*---------------------------------------------------------------------------*/
// static float exp_mov_avg(float new, float old) { return ALPHA * new + (1 - ALPHA) * old; }