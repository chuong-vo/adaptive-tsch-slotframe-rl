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
 * \addtogroup sdn-advertisement
 * @{
 *
 * @file sdn-advertisement.c
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief Header for the Contiki/SD-WSN neighbor advertisement
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#include "net/sdn-net/sdn-advertisement.h"
#include "net/sdn-net/sdn-net.h"
#include "net/packetbuf.h"
#include "lib/random.h"
#include "net/sdn-net/sd-wsn.h"
#include "net/sdn-net/sdn.h"
#include "net/link-stats.h"
#include <string.h>
#include "net/sdn-net/sdn-ds-nbr.h"
#include "net/sdn-net/sdn-ds-route.h"
#include "net/sdn-net/sdn-neighbor-discovery.h"
#include "net/routing/routing.h"
#include "sdnbuf.h"
#if SDN_CONTROLLER
#include "sdn-controller/sdn-ds-node.h"
#include "sdn-controller/sdn-ds-config-routes.h"
#include "sdn-controller/sdn-ds-node-route.h"
#endif

#if BUILD_WITH_SDN_CONTROLLER_SERIAL
#include "sdn-serial.h"
#include "sdn-serial-protocol.h"
#endif /* BUILD_WITH_SDN_CONTROLLER_SERIAL */

#if !BUILD_WITH_SDN_CONTROLLER_SERIAL
#include "sdn-power-measurement.h"
#endif

/* Log configuration */
#include "sys/log.h"
#define LOG_MODULE "NA"
#if LOG_CONF_LEVEL_NA
#define LOG_LEVEL LOG_CONF_LEVEL_NA
#else
#define LOG_LEVEL LOG_LEVEL_NONE
#endif /* LOG_CONF_LEVEL_NA */

/** Period for uip-ds6 periodic task*/
#ifndef SDN_NA_CONF_PERIOD
#define SDN_NA_PERIOD (CLOCK_SECOND / 10)
#else
#define SDN_NA_PERIOD SDN_NA_CONF_PERIOD
#endif

#if !BUILD_WITH_SDN_CONTROLLER_SERIAL
// static sdn_na_adv_t na_pkt; //Holds the rank value and the total rssi value to the controller
struct timer na_timer_send; /**< NA timer, to schedule NA sending */
static uint32_t rand_time;  /**< random time value for timers */
static uint16_t cycle_seq = 0;
static uint8_t seq = 0;
#endif /* !BUILD_WITH_SDN_CONTROLLER_SERIAL */

// int send_advertisement; // Send advertisement flag.

struct etimer na_timer_periodic;

/*---------------------------------------------------------------------------*/
#if !BUILD_WITH_SDN_CONTROLLER_SERIAL
static void print_na_packet()
{

    print_buff(sdn_buf, sdn_len, true);

    /* Print header */
    LOG_INFO("---------SDN-NA-PACKET--------------\n");
    LOG_INFO("payload length: %d (0x%02x)\n", SDN_NA_BUF->payload_len, SDN_NA_BUF->payload_len);
    LOG_INFO("rank: %d (0x%02x)\n", SDN_NA_BUF->rank, SDN_NA_BUF->rank);
    LOG_INFO("power: %u (0x%04x)\n", sdnip_htons(SDN_NA_BUF->energy), sdnip_htons(SDN_NA_BUF->energy));
    LOG_INFO("cycle sequence: %u (0x%04x)\n", sdnip_htons(SDN_NA_BUF->cycle_seq), sdnip_htons(SDN_NA_BUF->cycle_seq));
    LOG_INFO("sequence: %u (0x%02x)\n", SDN_NA_BUF->seq, SDN_NA_BUF->seq);
    LOG_INFO("checksum: 0x%04x\n", sdnip_htons(SDN_NA_BUF->pkt_chksum));

    /* Print payload */
    print_buff(sdn_buf + SDN_IPH_LEN + SDN_NAH_LEN, SDN_NA_BUF->payload_len, 0);
    LOG_INFO("----------------------------------------\n");
}
#endif /* # BUILD_WITH_SDN_CONTROLLER_SERIAL */
/*---------------------------------------------------------------------------*/
#if SDN_DS_NBR_NOTIFICATIONS
static void
neighbor_callback(int event, const sdn_ds_nbr_t *nbr)
{
    if (event == SDN_DS_NBR_NOTIFICATION_ADD)
    {
#if !(SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL)
        // PRINTF("adding neighbor, send NA\n");
        // send_advertisement = 1;
        // PRINTF("Sending NA because adding\n");
#endif
    }
    else if (event == SDN_DS_NBR_NOTIFICATION_RM)
    {
#if !(SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL)
        // PRINTF("removing neighbor, send NA\n");
        // send_advertisement = 1;
        // PRINTF("Sending NA because removing\n");
#endif
    }
    else if (event == SDN_DS_NBR_NOTIFICATION_CH)
    {
#if !(SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL)
        // PRINTF("neighbor changed, send NA\n");
        // send_advertisement = 1;
        // PRINTF("Sending NA because nb changed\n");
#endif
    }
    /* Give extra time to network settle down */
    // #if !SDN_CONTROLLER
    //     stimer_set(&na_timer_send, rand_time);
    // #endif
}
#endif
/*---------------------------------------------------------------------------*/
void sdn_na_init(void)
{
    etimer_set(&na_timer_periodic, SDN_NA_PERIOD);
#if !BUILD_WITH_SDN_CONTROLLER_SERIAL
    timer_set(&na_timer_send, 2); /* wait to have a link local IP address */
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
#if !BUILD_WITH_SDN_CONTROLLER_SERIAL
static void send_na_output(void)
{
    const linkaddr_t *nxthop;
    const struct link_stats *stats;
    nxthop = NETSTACK_ROUTING.nexthop(&ctrl_addr);
    if (nxthop != NULL)
    {
        /* payload size */
        int8_t payload_size = SDN_NAPL_LEN * sdn_ds_nbr_num();
        LOG_INFO("Sending NA packet\n");
        /* IP packet */
        SDN_IP_BUF->vap = (0x01 << 5) | SDN_PROTO_NA;
        /* Total length */
        sdn_len = SDN_IPH_LEN + SDN_NAH_LEN + payload_size;
        SDN_IP_BUF->tlen = sdn_len;
        SDN_IP_BUF->ttl = 0x40;
        SDN_IP_BUF->scr.u16 = sdnip_htons(linkaddr_node_addr.u16);
        SDN_IP_BUF->dest.u16 = sdnip_htons(ctrl_addr.u16);
        SDN_IP_BUF->hdr_chksum = 0;
        SDN_IP_BUF->hdr_chksum = ~sdn_ipchksum();
        /* NA packet */
        seq++;
        SDN_NA_BUF->payload_len = payload_size;
        SDN_NA_BUF->rank = my_rank.rank;
        SDN_NA_BUF->energy = sdnip_htons((int16_t)moving_avg_power);
        SDN_NA_BUF->cycle_seq = sdnip_htons(cycle_seq);
        SDN_NA_BUF->seq = seq;

        /* Put neighbor's info in payload */
        sdn_ds_nbr_t *nbr;
        uint8_t count = 0;

        for (nbr = sdn_ds_nbr_head(); nbr != NULL; nbr = sdn_ds_nbr_next(nbr))
        {
            SDN_NA_PAYLOAD(count)->nb_addr.u16 = sdnip_htons(nbr->addr.u16);
            // We get the ETX, RSSI values from link-stats.c
            stats = link_stats_from_lladdr(&nbr->addr);
            if (stats != NULL)
            {
                SDN_NA_PAYLOAD(count)->rssi = sdnip_htons(stats->rssi);
                SDN_NA_PAYLOAD(count)->etx = sdnip_htons(stats->etx);
            }
            else
            {
                SDN_NA_PAYLOAD(count)->rssi = sdnip_htons(0);
                SDN_NA_PAYLOAD(count)->etx = sdnip_htons(0);
            }
            count++;
        }

        SDN_NA_BUF->pkt_chksum = 0;
        SDN_NA_BUF->pkt_chksum = ~sdn_nachksum(payload_size);

        /* Update statistics */
        SDN_STAT(++sdn_stat.ip.sent);
        SDN_STAT(++sdn_stat.cp.adv);
        SDN_STAT(sdn_stat.cp.adv_bytes += sdn_len);

        print_na_packet();

        sdnbuf_set_attr(SDNBUF_ATTR_MAX_MAC_TRANSMISSIONS, 3);

        sdn_ip_output(nxthop);
    }
}
#endif
/*---------------------------------------------------------------------------*/
#if !BUILD_WITH_SDN_CONTROLLER_SERIAL
void sdn_na_reset_seq(uint16_t new_cycle_seq)
{
    cycle_seq = new_cycle_seq;
    seq = 0;
}
#endif
/*---------------------------------------------------------------------------*/
#if !BUILD_WITH_SDN_CONTROLLER_SERIAL
static void sdn_send_na_periodic(void)
{
    // if (send_advertisement)
    // {
    send_na_output();
    // send_advertisement = 0;
    // }
    uint32_t interval =  SDN_MAX_NA_INTERVAL * CLOCK_SECOND;
    uint32_t jitter_time = random_rand() % (CLOCK_SECOND);
    rand_time = interval + jitter_time;
    // LOG_INFO("Random time = %lu\n", rand_time);
    timer_set(&na_timer_send, rand_time);
}
#endif
/*---------------------------------------------------------------------------*/
void sdn_na_periodic(void)
{
/* Periodic ND sending */
// PRINTF("periodic.\n");
#if !BUILD_WITH_SDN_CONTROLLER_SERIAL
    if (timer_expired(&na_timer_send) /* && (sdn_len == 0) */)
    {
        sdn_send_na_periodic();
    }
#endif
    etimer_reset(&na_timer_periodic);
}

/** @} */