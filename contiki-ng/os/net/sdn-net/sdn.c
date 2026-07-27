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
 * \addtogroup sdn
 * @{
 *
 * @file sdn.c
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief sdn processing
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#include "sdn.h"
#include "net/netstack.h"
#include "net/linkaddr.h"
#include "net/routing/routing.h"
#include "sd-wsn.h"
#include "sdnbuf.h"
#include "sdn-neighbor-discovery.h"
#include "sdn-advertisement.h"
// #include "sdn-network-config.h"
#include "sdn-data-packets.h"

#if BUILD_WITH_SDN_CONTROLLER_SERIAL
#include "sdn-controller-serial/sdn-serial.h"
#include "sdn-controller-serial/sdn-serial-protocol.h"
#include <string.h>
#endif /* BUILD_WITH_SDN_CONTROLLER_SERIAL */

/* Log configuration */
#include "sys/log.h"
#define LOG_MODULE "SDN"
#if LOG_CONF_LEVEL_SDN
#define LOG_LEVEL LOG_CONF_LEVEL_SDN
#else
#define LOG_LEVEL LOG_LEVEL_NONE
#endif /* LOG_CONF_LEVEL_SDN */

process_event_t sdn_event;
process_event_t nd_event;

enum
{
    PACKET_INPUT
};

/* Periodic check of active connections. */
static struct etimer periodic;

static void packet_input(void);

PROCESS(sdn_process, "SDN stack");

/*---------------------------------------------------------------------------*/
void sdn_output()
{
    const linkaddr_t *nexthop;
    linkaddr_t dest;
    if (sdn_len == 0)
    {
        return;
    }

    if (((linkaddr_t *)&SDN_IP_BUF->dest) == NULL)
    {
        LOG_INFO("output: Destination address unspecified");
        goto exit;
    }

    /* We first check if the destination address is one of ours. There is no
     * loopback interface -- instead, process this directly as incoming. */
    if (linkaddr_cmp(&SDN_IP_BUF->dest, &linkaddr_node_addr))
    {
        LOG_INFO("output: sending to ourself\n");
        packet_input();
        return;
    }

    /* Look for a next hop */
    if ((SDN_IP_BUF->vap == ((0x01 << 5) | SDN_PROTO_SA)) ||
        (SDN_IP_BUF->vap == ((0x01 << 5) | SDN_PROTO_RA)))
    {
        goto netflood;
    }
    dest.u16 = sdnip_htons(SDN_IP_BUF->dest.u16);
    nexthop = NETSTACK_ROUTING.nexthop(&dest);
    // nexthop = NULL;
    if (nexthop == NULL)
    {
#if BUILD_WITH_SDN_CONTROLLER_SERIAL
        // Check if this packet needs to be forwarded to the serial controller
        if (linkaddr_cmp(&ctrl_addr, &dest))
        {
            // Forward packet to serial interface
            LOG_INFO("Forwarding packet to serial interface\n");
            serial_ip_output();
        }
#endif /* BUILD_WITH_SDN_CONTROLLER_SERIAL */
        goto sent;
    }
    LOG_INFO("output: sending to %d.%d\n",
           nexthop->u8[0], nexthop->u8[1]);

    sdn_ip_output(nexthop);

    goto sent;

netflood:
    sdn_ip_output(NULL);
    sdn_ip_output(NULL);

sent:
    LOG_INFO("output: packet forwarded\n");
    // sdnbuf_clear();
    return;

exit:
    LOG_INFO("output: packet not forwarded\n");
    sdnbuf_clear();
    return;
}
/*---------------------------------------------------------------------------*/
static void
packet_input(void)
{
    if (sdn_len > 0)
    {
        LOG_INFO("input: received %u bytes\n", sdn_len);
        sdn_input();
        if (sdn_len > 0)
        {
            sdn_output();
        }
    }
}
/*---------------------------------------------------------------------------*/
void sdn_ip_input(void)
{
    if (netstack_process_ip_callback(NETSTACK_IP_INPUT, NULL) ==
        NETSTACK_IP_PROCESS)
    {
        process_post_synch(&sdn_process, PACKET_INPUT, NULL);
    } /* else - do nothing and drop */
    sdnbuf_clear();
}
/*---------------------------------------------------------------------------*/
#if BUILD_WITH_SDN_CONTROLLER_SERIAL
void serial_ip_output()
{
    if (sdn_len == 0)
    {
        return;
    }
    linkaddr_t from;
    /* Get the sender node address */
    from.u16 = sdnip_htons(SDN_IP_BUF->scr.u16);
    sdn_serial_len = SDN_SERIAL_PACKETH_LEN + SDN_IP_BUF->tlen;
    SDN_SERIAL_PACKET_BUF->addr = from;
    SDN_SERIAL_PACKET_BUF->pkt_chksum = 0x0000;
    SDN_SERIAL_PACKET_BUF->type = SDN_SERIAL_MSG_TYPE_CP;
    SDN_SERIAL_PACKET_BUF->payload_len = SDN_IP_BUF->tlen;
    SDN_SERIAL_PACKET_BUF->reserved[0] = 0;
    SDN_SERIAL_PACKET_BUF->reserved[1] = 0;
    // copy payload to send serial buffer
    memcpy(SDN_SERIAL_PACKET_PAYLOAD_BUF(0), SDN_IP_BUF, SDN_IP_BUF->tlen);
    serial_packet_output();
}
#endif /* BUILD_WITH_SDN_CONTROLLER_SERIAL */
/*---------------------------------------------------------------------------*/
uint8_t sdn_ip_output(const linkaddr_t *dest)
{
    if (sdn_len == 0)
    {
        return 0;
    }
    int ret;
    if (netstack_process_ip_callback(NETSTACK_IP_OUTPUT, (const linkaddr_t *)dest) ==
        NETSTACK_IP_PROCESS)
    {
        ret = NETSTACK_NETWORK.output(dest);
        return ret;
    }
    else
    {
        /* Ok, ignore and drop... */
        sdnbuf_clear();
        return 0;
    }
}
/*---------------------------------------------------------------------------*/
static void
eventhandler(process_event_t ev, process_data_t data)
{
    // LOG_INFO("SDN event\n");
    switch (ev)
    {
    case PROCESS_EVENT_TIMER:
        /* We get this event if one of our timers have expired. */
        {
            if (data == &nd_timer_periodic &&
                etimer_expired(&nd_timer_periodic))
            {
                sdn_nd_periodic();
                // tcpip_ipv6_output();
            }
#if !(SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL)
            if (data == &data_timer_periodic &&
                etimer_expired(&data_timer_periodic))
            {
                sdn_data_periodic();
            }
#endif
            if (data == &na_timer_periodic &&
                etimer_expired(&na_timer_periodic))
            {
                sdn_na_periodic();
                // tcpip_ipv6_output();
            }
#if SDN_CONTROLLER
            if (data == &nc_timer_periodic &&
                etimer_expired(&nc_timer_periodic))
            {
                sdn_nc_periodic(); // Network configuration
            }
#endif
            if (data == &sdn_ds_timer_periodic &&
                etimer_expired(&sdn_ds_timer_periodic))
            {
                sdn_ds_periodic();
                // tcpip_ipv6_output();
            }
        }
        break;
    case PACKET_INPUT:
        packet_input();
        break;
    }
}
/*---------------------------------------------------------------------------*/
PROCESS_THREAD(sdn_process, ev, data)
{
    PROCESS_BEGIN();
    LOG_INFO("SDN started.\n");

    sdn_event = process_alloc_event();
    nd_event = process_alloc_event();

    etimer_set(&periodic, CLOCK_SECOND / 2);

    /* Initialize routing protocol */
    /* Initialize routing protocol */
    NETSTACK_ROUTING.init();

    /* Clear uipbuf and set default attributes */
    sdnbuf_clear();

    sdn_wsn_init();

    while (1)
    {
        PROCESS_YIELD();
        eventhandler(ev, data);
    }

    PROCESS_END();
}

/** @} */