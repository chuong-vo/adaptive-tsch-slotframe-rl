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
 * \addtogroup sdn-neighbor-discovery
 * @{
 *
 * @file sdn-neighbor-discovery.h
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief Header for the Contiki/SD-WSN interface
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#include "sdn-neighbor-discovery.h"
#include "sdn-net.h"
#include "net/packetbuf.h"
#include "lib/random.h"
#include "sd-wsn.h"
#include "sdn.h"
#include <string.h>
#include "sdn-ds-nbr.h"
#include "sdn-ds-route.h"
#include "sdnbuf.h"
#include "net/link-stats.h"

#if BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED
#include "services/orchestra-sdn-centralised/orchestra.h"
#endif /* BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED */

#if BUILD_WITH_SDN_ORCHESTRA
#include "services/orchestra-sdn/orchestra.h"
#endif /* BUILD_WITH_SDN_ORCHESTRA */

/* Log configuration */
#include "sys/log.h"
#define LOG_MODULE "ND"
#if LOG_CONF_LEVEL_ND
#define LOG_LEVEL LOG_CONF_LEVEL_ND
#else
#define LOG_LEVEL LOG_LEVEL_NONE
#endif /* LOG_CONF_LEVEL_ND */

/** Period for uip-ds6 periodic task*/
#ifndef SDN_ND_CONF_PERIOD
#define SDN_ND_PERIOD (CLOCK_SECOND / 10)
#else
#define SDN_ND_PERIOD SDN_ND_CONF_PERIOD
#endif

// #if !(SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL)
sdn_rank_t my_rank; // Holds the rank value and the total rssi value to the controller
// #endif

struct etimer nd_timer_periodic;
struct timer nd_timer_send; /**< ND timer, to schedule ND sending */
static uint32_t rand_time;  /**< random time value for timers */

/*---------------------------------------------------------------------------*/
#if SDN_DS_NBR_NOTIFICATIONS
static void
neighbor_callback(int event, const sdn_ds_nbr_t *nbr)
{
    if (event == SDN_DS_NBR_NOTIFICATION_RM)
    {
#if !(SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL)
        LOG_INFO("removing neighbor %d.%d, check whether is gtw to ctrl\n",
                 nbr->addr.u8[0], nbr->addr.u8[1]);
        if (linkaddr_cmp(&my_rank.addr, &nbr->addr))
        {
            LOG_INFO("removing gtw to ctrl\n");
            my_rank.rank = 0xff;
            my_rank.rssi = 0;
            /* Remove route to ctrl */
            sdn_ds_route_rm_by_nexthop(&ctrl_addr);
        }
#endif
    }
}
#endif
/*---------------------------------------------------------------------------*/
#if !(SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL)
static void update_rank(int16_t rssi, uint8_t rank, const linkaddr_t *from)
{
    // if (my_rank.rank > 1)
    if (sdn_ds_route_add(&ctrl_addr, rssi, from, SDN_NODE) == NULL)
        LOG_INFO("rank route could not be updated, locked by ctrl\n");
    // else
    // {
    my_rank.rank = rank + 1;
    my_rank.rssi = rssi;
    linkaddr_copy(&my_rank.addr, from);
    LOG_INFO("rank updated: rank %d total rssi %d\n", my_rank.rank, my_rank.rssi);
    LOG_INFO(" gw address = %d.%d\n", my_rank.addr.u8[0], my_rank.addr.u8[1]);
#if BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED || BUILD_WITH_SDN_ORCHESTRA
    tsch_queue_update_time_source(from);
    NETSTACK_CONF_SDN_RANK_UPDATED_CALLBACK(from, my_rank.rank);
#endif /* BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED || BUILD_WITH_SDN_ORCHESTRA */
    // }
}
#endif
/*---------------------------------------------------------------------------*/
void sdn_nd_init(void)
{
    etimer_set(&nd_timer_periodic, SDN_ND_PERIOD);
    timer_set(&nd_timer_send, 2); /* wait to have a link local IP address */
#if !(SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL)
    my_rank.rank = 0xff; /* Sensor node */
    my_rank.rssi = 0x00;
#else
    my_rank.rank = 0x00; /* Sensor node */
    my_rank.rssi = 0x00;
#endif
/* callback function when neighbor removed */
#if SDN_DS_NBR_NOTIFICATIONS
    static struct sdn_ds_nbr_notification n;
    sdn_ds_nbr_notification_add(&n,
                                neighbor_callback);
#endif
    return;
}
/*---------------------------------------------------------------------------*/
void sdn_nd_input(void)
{
    int16_t ndRank, ndRssi, rssi;
    const struct link_stats *stats;
    const linkaddr_t *addr;
    addr = packetbuf_addr(PACKETBUF_ADDR_SENDER);
    // We get the ETX, RSSI values from link-stats.c
    stats = link_stats_from_lladdr(addr);
    if (stats != NULL)
    {
        rssi = stats->rssi;
    }
    else
    {
        rssi = (int16_t)sdn_net_get_last_rssi();
    }
    ndRank = sdn_ntohs(SDN_ND_BUF->rank);
    ndRssi = sdn_ntohs(SDN_ND_BUF->rssi);

    LOG_INFO("Processing ND packet with rcv rssi %d and rank %d and rssi to ctrl %d\n",
             rssi,
             ndRank,
             ndRssi);

#if !(SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL)
    /* Check whether the ND message is
     * from the gateway. If it is, we need
     * to update the rank
     * */
    if (linkaddr_cmp(addr,
                     &my_rank.addr))
    {
        if (ndRank == 255)
        {
            my_rank.rank = 0xff;
            my_rank.rssi = 0;
            /* Remove route to ctrl */
            sdn_ds_route_rm_by_nexthop(&ctrl_addr);
        }
        else
        {
            update_rank(ndRssi + rssi,
                        ndRank,
                        addr);
        }
    }
    else if (ndRank == my_rank.rank - 1)
    {
        LOG_INFO("rank equal.\n");
        /* acc rssi is greater? */
        if (ndRssi + rssi > my_rank.rssi)
        {
            LOG_INFO("better link quality\n");
            update_rank(ndRssi + rssi, ndRank, addr);
        }
    }
    else if (ndRank < my_rank.rank - 1)
    {
        update_rank(ndRssi + rssi, ndRank, addr);
    }
#endif
    sdn_ds_nbr_add(addr, &ndRank, &ndRssi, &rssi, NULL);
}
/*---------------------------------------------------------------------------*/
static void send_nd_output(void)
{
    /* IP packet */
    SDN_IP_BUF->vap = (0x01 << 5) | SDN_PROTO_ND;
    /* Total length */
    sdn_len = SDN_IPH_LEN + SDN_NDH_LEN;
    SDN_IP_BUF->tlen = sdn_len;

    SDN_IP_BUF->ttl = 0x40;

    SDN_IP_BUF->scr.u16 = sdnip_htons(linkaddr_node_addr.u16);

    SDN_IP_BUF->dest.u16 = sdnip_htons(linkaddr_null.u16);

    SDN_IP_BUF->hdr_chksum = 0;
    SDN_IP_BUF->hdr_chksum = ~sdn_ipchksum();

    /* ND packet */
#if !(SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL)
    SDN_ND_BUF->rank = sdnip_htons(my_rank.rank);
    SDN_ND_BUF->rssi = sdnip_htons(my_rank.rssi);
#else
    SDN_ND_BUF->rank = 0;
    SDN_ND_BUF->rssi = 0;
#endif

    SDN_ND_BUF->ndchksum = 0;
    SDN_ND_BUF->ndchksum = ~sdn_ndchksum();

    // print_buff(sdn_buf, sdn_len, true);

    LOG_INFO("Sending ND packet (rank: %d, rssi: %d)\n",
             sdn_ntohs(SDN_ND_BUF->rank),
             sdn_ntohs(SDN_ND_BUF->rssi));

    /* Update statistics */
    SDN_STAT(++sdn_stat.ip.sent);
    SDN_STAT(++sdn_stat.nd.sent);
    SDN_STAT(sdn_stat.nd.sent_bytes += sdn_len);

    // sdnbuf_set_attr(SDNBUF_ATTR_MAX_MAC_TRANSMISSIONS, 3);

    sdn_ip_output(NULL);
}
/*---------------------------------------------------------------------------*/
static void sdn_send_nd_periodic(void)
{
    send_nd_output();
    LOG_INFO("sending ND message.\n");
    uint32_t interval =  SDN_MAX_ND_INTERVAL * CLOCK_SECOND;
    uint32_t jitter_time = random_rand() % (CLOCK_SECOND);
    rand_time = interval + jitter_time;
    // LOG_INFO("Random time 1 = %lu\n", rand_time);
    timer_set(&nd_timer_send, rand_time);
}
/*---------------------------------------------------------------------------*/
void sdn_nd_periodic(void)
{
    /* Periodic ND sending */
    // LOG_INFO("periodic.\n");
    if (timer_expired(&nd_timer_send) /* && (sdn_len == 0) */)
    {
        sdn_send_nd_periodic();
    }
    etimer_reset(&nd_timer_periodic);
}

/** @} */