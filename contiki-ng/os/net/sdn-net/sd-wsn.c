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
 * \addtogroup sdwsn
 * @{
 *
 * @file sd-wsn.c
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief Header for the Contiki/SD-WSN interface
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#include "sd-wsn.h"
#include "sdnbuf.h"
#include "sdn-neighbor-discovery.h"
#include "sdn-advertisement.h"
#include "sdn-ds-nbr.h"
#include "net/ipv6/uip.h" // show this header be here?
#include "sdn-ds-route.h"
// #include "sdn-network-config.h"
#include "sdn-data-packets.h"
// #include "sdn-data-aggregation.h"
#include "sdn-route-advertisement.h"
#include "sdn-schedule-advertisement.h"
#if SDN_CONTROLLER
#include "sdn-controller/sdn-ds-node-route.h"
#include "sdn-controller/sdn-ds-config-routes.h"
#include "sdn-controller/sdn-ds-edge.h"
#include "sdn-controller/sdn-ds-node.h"
#include "sdn-controller/sdn-ds-dfs.h"
#endif
#if BUILD_WITH_SDN_CONTROLLER_SERIAL
#include "sdn-serial.h"
#endif /* BUILD_WITH_SDN_CONTROLLER_SERIAL */
#if BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED || BUILD_WITH_SDN_ORCHESTRA
#include "net/mac/tsch/tsch.h"
// #include "net/mac/tsch/tsch-asn.h"
#endif /* BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED || BUILD_WITH_SDN_ORCHESTRA */

/* Log configuration */
#include "sys/log.h"
#define LOG_MODULE "SD-WSN"
#if LOG_CONF_LEVEL_SDWSN
#define LOG_LEVEL LOG_CONF_LEVEL_SDWSN
#else
#define LOG_LEVEL LOG_LEVEL_NONE
#endif /* LOG_CONF_LEVEL_SDWSN */

#if SDN_STATISTICS == 1
struct sdn_stats sdn_stat;
#endif

struct etimer sdn_ds_timer_periodic; /**< Timer for maintenance of data structures */

uint16_t sdn_len;
sdn_buf_t sdn_aligned_buf;

/*---------------------------------------------------------------------------*/
void sdn_wsn_init(void)
{
    sdnbuf_init();
    sdn_nd_init();
    sdn_ds_neighbors_init();
    sdn_ds_route_init();
    sdn_na_init();
    sdn_data_init();
    // sdn_data_aggregation_init();
#if SDN_CONTROLLER
    sdn_ds_node_id_init();
    sdn_nc_init();
    sdn_ds_node_route_init();
    sdn_ds_edge_init();
    sdn_ds_config_routes_init();
    sdn_ds_node_init();
    dfs_init();
#endif
    etimer_set(&sdn_ds_timer_periodic, SDN_DS_PERIOD);
}
/*---------------------------------------------------------------------------*/
void print_buff(uint8_t *buf, size_t buflen, int8_t bare)
{
    // PRINTF("sof dump.\n");
    if (bare)
    {
        LOG_INFO("Dump: ");
        while (buflen--)
            LOG_INFO_("%02X%s", *buf++, (buflen > 0) ? " " : "");
        LOG_INFO_("\n");
    }
    else
    {
        LOG_INFO("Dump: ");
        while (buflen--)
            LOG_INFO_("%02X%s", *buf++, (buflen > 0) ? " " : "");
        LOG_INFO_("\n");
    }
    // PRINTF("\n");
}
/*---------------------------------------------------------------------------*/
static uint16_t
chksum(uint16_t sum, const uint8_t *data, uint16_t len)
{
    uint16_t t;
    const uint8_t *dataptr;
    const uint8_t *last_byte;

    dataptr = data;
    last_byte = data + len - 1;

    while (dataptr < last_byte)
    { /* At least two more bytes */
        t = (dataptr[0] << 8) + dataptr[1];
        sum += t;
        if (sum < t)
        {
            sum++; /* carry */
        }
        dataptr += 2;
    }

    if (dataptr == last_byte)
    {
        t = (dataptr[0] << 8) + 0;
        sum += t;
        if (sum < t)
        {
            sum++; /* carry */
        }
    }

    /* Return sum in host byte order. */
    return sum;
}
/*---------------------------------------------------------------------------*/
/*---------------------------------------------------------------------------*/
uint16_t
sdnip_htons(uint16_t val)
{
    return UIP_HTONS(val);
}
/*---------------------------------------------------------------------------*/
uint16_t
sdn_ipchksum(void)
{
    uint16_t sum;

    sum = chksum(0, sdn_buf, SDN_IPH_LEN);
    LOG_DBG("sdn_ipchksum: sum 0x%04x\n", sum);
    return (sum == 0) ? 0xffff : sdnip_htons(sum);
}
/*---------------------------------------------------------------------------*/
uint16_t sdn_ndchksum(void)
{
    uint16_t sum;

    sum = chksum(0, SDN_IP_PAYLOAD(0), SDN_NDH_LEN);
    LOG_DBG("sdn_ndchksum: sum 0x%04x\n", sum);
    return (sum == 0) ? 0xffff : sdnip_htons(sum);
}
/*---------------------------------------------------------------------------*/
uint16_t sdn_nachksum(uint8_t len)
{
    uint16_t sum;

    sum = chksum(0, SDN_IP_PAYLOAD(0), SDN_NAH_LEN + len);
    LOG_DBG("sdn_nachksum: sum 0x%04x\n", sum);
    return (sum == 0) ? 0xffff : sdnip_htons(sum);
}
/*---------------------------------------------------------------------------*/
uint16_t sdn_rachksum(uint8_t len)
{
    uint16_t sum;

    sum = chksum(0, SDN_IP_PAYLOAD(0), SDN_RAH_LEN + len);
    LOG_DBG("sdn_rachksum: sum 0x%04x\n", sum);
    return (sum == 0) ? 0xffff : sdnip_htons(sum);
}
/*---------------------------------------------------------------------------*/
uint16_t sdn_sachksum(uint8_t len)
{
    uint16_t sum;

    sum = chksum(0, SDN_IP_PAYLOAD(0), SDN_SAH_LEN + len);
    LOG_DBG("sdn_sachksum: sum 0x%04x\n", sum);
    return (sum == 0) ? 0xffff : sdnip_htons(sum);
}
/*---------------------------------------------------------------------------*/
void sdn_ds_periodic(void)
{
#if SDN_CONTROLLER
    /* Periodic processing on default routers */
    sdn_ds_node_periodic();
    sdn_ds_node_route_periodic();
#endif
    sdn_ds_neighbor_periodic();
    etimer_reset(&sdn_ds_timer_periodic);
}
/*---------------------------------------------------------------------------*/
static bool sdn_update_ttl(void)
{
    if (SDN_IP_BUF->ttl <= 1)
    {
        // uip_icmp6_error_output(ICMP6_TIME_EXCEEDED, ICMP6_TIME_EXCEED_TRANSIT, 0);
        SDN_STAT(++sdn_stat.ip.drop);
        return false;
    }
    else
    {
        SDN_IP_BUF->ttl = SDN_IP_BUF->ttl - 1;
        return true;
    }
}
/*---------------------------------------------------------------------------*/
void sdnip_process(uint8_t flag)
{
    uint8_t protocol;
    uint8_t *next_header;
    linkaddr_t dest;

#if BUILD_WITH_SDN_CONTROLLER_SERIAL
    struct tsch_asn_t data_asn;
#endif /* BUILD_WITH_SDN_CONTROLLER_SERIAL */

    print_buff(sdn_buf, sdn_len, true);

    /* This is where the input processing starts. */
    SDN_STAT(++sdn_stat.ip.recv);

    /* Compute IP layer checksum */
    if (sdn_ipchksum() != 0xffff)
    {
        SDN_STAT(++sdn_stat.ip.drop);
        SDN_STAT(++sdn_stat.ip.chkerr);
        LOG_WARN("ip bad checksum\n");
        goto drop;
    }

    /*
     * If the reported length in the ip header doesn't match the packet size,
     * then we drop the packet.
     */
    if (sdn_len < sdnbuf_get_len_field(SDN_IP_BUF))
    {
        SDN_STAT(++sdn_stat.ip.drop);
        LOG_WARN("packet shorter than reported in IP header\n");
        goto drop;
    }

    /* Check that the packet length is acceptable given our IP buffer size. */
    if (sdn_len > sizeof(sdn_buf))
    {
        SDN_STAT(++sdn_stat.ip.drop);
        LOG_WARN("dropping packet with length %d > %d\n",
                 (int)sdn_len, (int)sizeof(sdn_buf));
        goto drop;
    }

    /*
     * Process Packets with a routable multicast destination:
     * - We invoke the multicast engine and let it do its thing
     *   (cache, forward etc).
     * - We never execute the datagram forwarding logic in this file here. When
     *   the engine returns, forwarding has been handled if and as required.
     * - Depending on the return value, we either discard or deliver up the stack
     *
     * All multicast engines must hook in here. After this function returns, we
     * expect UIP_BUF to be unmodified
     */

    dest.u16 = sdn_ntohs(SDN_IP_BUF->dest.u16);

    if (!linkaddr_cmp(&dest, &linkaddr_node_addr) &&
        !linkaddr_cmp(&dest, &linkaddr_null))
    {

        LOG_INFO("sdn ip packet Not for us from ");
        LOG_INFO_LLADDR(&SDN_IP_BUF->scr);
        LOG_INFO_("\n");

        if (!sdn_update_ttl())
        {
            LOG_WARN("ttl expired\n");
            SDN_STAT(++sdn_stat.nd.drop);
            goto drop;
        }
        /* If this is a data packet received at the sink. Then, calculate the
        ASN difference (useful for delay calcaulation at the controller)*/
#if BUILD_WITH_SDN_CONTROLLER_SERIAL
        if ((SDN_IP_BUF->vap & 0x0F) == SDN_PROTO_DATA)
        {
            uint16_t asn_ls4b_lsb = packetbuf_attr(PACKETBUF_ATTR_RX_ASN_LSB4B_LSB);
            uint16_t asn_ls4b_msb = packetbuf_attr(PACKETBUF_ATTR_RX_ASN_LSB4B_MSB);
            uint16_t asn_ms1b = packetbuf_attr(PACKETBUF_ATTR_RX_ASN_MS1B);
            struct tsch_asn_t tsch_rx_asn;
            tsch_rx_asn.ls4b = asn_ls4b_msb << 16 | asn_ls4b_lsb;
            tsch_rx_asn.ms1b = asn_ms1b;
            // LOG_INFO("tsch_rx_asn %02x.%08" PRIx32 "\n", tsch_rx_asn.ms1b, tsch_rx_asn.ls4b);
            // LOG_INFO("current tsch asn %02x.%08" PRIx32 "\n", tsch_current_asn.ms1b, tsch_current_asn.ls4b);
            data_asn.ls4b = sdnip_htons(SDN_DATA_BUF->asn_ls4b_msb);
            data_asn.ls4b = data_asn.ls4b << 16;
            data_asn.ls4b = data_asn.ls4b | sdnip_htons(SDN_DATA_BUF->asn_ls4b_lsb);
            // Because we subtract the ASN of the packet from the current ASN, the MS1B of
            // the packet ASN is always 0
            data_asn.ms1b = 0;
            // LOG_INFO("rcv tsch asn %02x.%08" PRIx32 "\n", data_asn.ms1b, data_asn.ls4b);
            data_asn.ls4b = TSCH_ASN_DIFF(tsch_rx_asn, data_asn);
            // LOG_INFO("Difference:  %02x.%08" PRIx32 ".\n", data_asn.ms1b, data_asn.ls4b);
            // LOG_INFO("Difference:  %u.\n", data_asn.ls4b);
            SDN_DATA_BUF->asn_ls4b_lsb = sdnip_htons(data_asn.ls4b & 0x0000FFFF);
            SDN_DATA_BUF->asn_ls4b_msb = sdnip_htons(data_asn.ls4b >> 16);
            SDN_DATA_BUF->asn_ms1b = 0;
        }
#endif /* BUILD_WITH_SDN_CONTROLLER_SERIAL */
        LOG_INFO("Forwarding packet to destination %d.%d\n",
                 dest.u8[0], dest.u8[1]);
        SDN_STAT(++sdn_stat.ip.forwarded);
        goto send;
    }

    LOG_INFO("sdn ip packet for us from ");
    LOG_INFO_LLADDR(&SDN_IP_BUF->scr);
    LOG_INFO_("\n");

    next_header = sdnbuf_get_next_header(sdn_buf, sdn_len, &protocol);

    /* Process upper-layer input */
    if (next_header != NULL)
    {
        switch (protocol)
        {
        case SDN_PROTO_ND:
            /* ND input */
            goto nd_input;
        case SDN_PROTO_NA:
            /* NA input */
            goto na_input;
        case SDN_PROTO_RA:
            /* RA input */
            goto ra_input;
        case SDN_PROTO_SA:
            /* TSCH schedules input */
            goto sa_input;
        case SDN_PROTO_DATA:
            /* Data input */
            goto data_input;
            break;
        }
        LOG_WARN("Protocol not found.\n");
        SDN_STAT(++sdn_stat.nd.drop);
        goto drop;
    }
nd_input:
    /* Compute and check the ICMP header checksum */

    if (sdn_ndchksum() != 0xffff)
    {
        SDN_STAT(++sdn_stat.nd.drop);
        SDN_STAT(++sdn_stat.nd.chkerr);
        LOG_WARN("nd bad checksum\n");
        goto drop;
    }
    /* This is ND processing. */
    sdn_nd_input();
    SDN_STAT(++sdn_stat.nd.recv);
    LOG_INFO("ND input length %d\n", sdn_len);
    goto drop;
data_input:
#if SDN_CONTROLLER
    /* Process incoming data packet */
    sdn_data_input();
    // SDN_STAT(++sdn_stat.data.recv);
    LOG_INFO("Data input length %d\n", sdn_len);
    goto drop;
#endif
na_input:
#if SDN_CONTROLLER
    if (sdn_nachksum(nabuf_get_len_field(SDN_NA_BUF)) != 0xffff)
    {
        // SDN_STAT(++sdn_stat.nd.drop);
        // SDN_STAT(++sdn_stat.nd.chkerr);
        LOG_WARN("na bad checksum\n");
        goto drop;
    }
    /* This is NA processing. */
    sdn_na_input();
#endif
    goto drop;
sa_input:
    if (sdn_sachksum(srbuf_get_len_field(SDN_SA_BUF)) != 0xffff)
    {
        LOG_WARN("SA bad checksum\n");
        goto drop;
    }
    /* Process SR packet */
    if (sdn_sa_input())
    {
        goto send;
    }
    goto drop;

ra_input:
    if (sdn_rachksum(ncbuf_get_len_field(SDN_RA_BUF)) != 0xffff)
    {
        LOG_WARN("RA bad checksum\n");
        goto drop;
    }
    /* Process RA packet */
    if (sdn_ra_input())
    {
        goto send;
    }
    goto drop;
send:
    /* Recalculate the checksum */
    SDN_IP_BUF->hdr_chksum = 0;
    SDN_IP_BUF->hdr_chksum = ~sdn_ipchksum();
    LOG_INFO("Forwarding packet with length %d (%d)\n", sdn_len, sdnbuf_get_len_field(SDN_IP_BUF));

    SDN_STAT(++sdn_stat.ip.sent);
    return;
drop:
    sdnbuf_clear();
    return;
}

/** @} */