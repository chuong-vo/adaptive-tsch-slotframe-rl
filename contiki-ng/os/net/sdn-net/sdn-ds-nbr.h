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
 * @file sdn-ds-nbr.h
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief Data structures for neighbor table
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#ifndef SDN_DS_NEIGHBOR_H_
#define SDN_DS_NEIGHBOR_H_

#include "contiki.h"
#include "net/linkaddr.h"
#include "net/nbr-table.h"
#include "sys/stimer.h"

/** \brief Set the maximum number of neighbor cache entries */
#ifdef SDN_DS_NBR_CONF_MAX_NEIGHBOR_CACHES
#define SDN_DS_NBR_MAX_NEIGHBOR_CACHES SDN_DS_NBR_CONF_MAX_NEIGHBOR_CACHES
#else
#define SDN_DS_NBR_MAX_NEIGHBOR_CACHES \
    (NBR_TABLE_MAX_NEIGHBORS * UIP_DS6_NBR_MAX_6ADDRS_PER_NBR)
#endif /* SDN_DS_NBR_CONF_MAX_NEIGHBOR_CACHES */

/**
 * Notifications
 */
#ifndef SDN_CONF_DS_NBR_NOTIFICATIONS
#define SDN_DS_NBR_NOTIFICATIONS (SDN_DS_NBR_MAX_NEIGHBOR_CACHES != 0)
#else
#define SDN_DS_NBR_NOTIFICATIONS SDN_CONF_DS_NBR_NOTIFICATIONS
#endif

/** \brief The default nbr_table entry (when
 * UIP_DS6_NBR_MULTI_IPV6_ADDRS is disabled), that implements nbr
 * cache */
typedef struct sdn_ds_nbr
{
    /* The ->addr field holds the Rime address of the neighbor. */
    linkaddr_t addr;
    /* The ->addr field holds number of hops to controller. */
    int16_t rank;
    /* The ->last_rssi and ->last_lqi fields hold the Received Signal
     Strength Indicator (RSSI) and CC2420 Link Quality Indicator (LQI)
     values that are received for the incoming broadcast packets. */
    int16_t rssi;
    /* exponential averge of rssi */
    float exp_avg;
    /* neighbor timeout */
    struct stimer lifetime;
} sdn_ds_nbr_t;

#if SDN_DS_NBR_NOTIFICATIONS
/* Event constants for the uip-ds6 route notification interface. The
   notification interface allows for a user program to be notified via
   a callback when a NBR has been added or removed and when the
   system has added or removed a default route. */
#define SDN_DS_NBR_NOTIFICATION_ADD 0
#define SDN_DS_NBR_NOTIFICATION_RM 1
#define SDN_DS_NBR_NOTIFICATION_CH 2

typedef void (*sdn_ds_nbr_notification_callback)(int event,
                                                 const sdn_ds_nbr_t *nbr);
struct sdn_ds_nbr_notification
{
    struct sdn_ds_nbr_notification *next;
    sdn_ds_nbr_notification_callback callback;
};

void sdn_ds_nbr_notification_add(struct sdn_ds_nbr_notification *n,
                                 sdn_ds_nbr_notification_callback c);

void sdn_ds_nbr_notification_rm(struct sdn_ds_nbr_notification *n);
/*--------------------------------------------------*/
#endif


void sdn_ds_neighbors_init(void);

/**
 * Add a neighbor cache for a specified IPv6 address, which is
 *  associated with a specified link-layer address
 * \param from the address of a neighbor to add
 * \param nbRank neighbour rank
 * \param nbRssi neighbour RSSI
 * \param rcv_rssi received RSSI
 * \param data Set data associated with the nbr cache
 * \return the address of a newly added nbr cache on success, NULL on
 * failure
*/
sdn_ds_nbr_t *sdn_ds_nbr_add(const linkaddr_t *from,
                             int16_t *nbRank,
                             int16_t *nbRssi,
                             int16_t *rcv_rssi, void *data);
/**
 * Remove a neighbor cache
 * \param nbr the address of a neighbor cache to remove
 * \return 1 on success, 0 on failure (nothing was removed)
 */
int sdn_ds_nbr_rm(sdn_ds_nbr_t *nbr);

/**
 * Get the link-layer address associated with a specified nbr cache
 * \param nbr the address of a neighbor cache
 * \return pointer to the link-layer address on success, NULL on failure
 */
const linkaddr_t *sdn_ds_nbr_get_ll(const sdn_ds_nbr_t *nbr);

/**
 * Get the neighbor cache associated with a specified IPv6 address
 * \param addr address used as a search key
 * \return the pointer to a neighbor cache on success, NULL on failure
 */
sdn_ds_nbr_t *sdn_ds_nbr_lookup(const linkaddr_t *addr);

/**
 * Return the number of neighbor caches
 * \return the number of neighbor caches in use
 */
int sdn_ds_nbr_num(void);

/**
 * Get the first neighbor cache in nbr_table
 * \return the pointer to the first neighbor cache entry
 */
sdn_ds_nbr_t *sdn_ds_nbr_head(void);

/**
 * Get the next neighbor cache of a specified one
 * \param nbr the pointer to a neighbor cache
 * \return the pointer to the next one on success, NULL on failure
 */
sdn_ds_nbr_t *sdn_ds_nbr_next(sdn_ds_nbr_t *nbr);

/**
 * The housekeeping function called periodically
 */
void sdn_ds_neighbor_periodic(void);

#endif

/** @} */