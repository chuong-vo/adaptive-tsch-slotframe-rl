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
/*---------------------------------------------------------------------------*/
#ifndef PROJECT_CONF_H_
#define PROJECT_CONF_H_
/*---------------------------------------------------------------------------*/
#define UIP_CONF_BUFFER_SIZE 0
#define UIP_CONF_UDP 0
#define UIP_CONF_UDP_CONNS 0
#define UIP_CONF_ND6_AUTOFILL_NBR_CACHE 0
#define SICSLOWPAN_CONF_FRAG 0
#define SICSLOWPAN_CONF_COMPRESSION 0
/*---------------------------------------------------------------------------*/
/* Set neighbour discovery period */
#define SDN_CONF_MAX_ND_INTERVAL 20
/* Set neighbour advertisement period */
#define SDN_CONF_MAX_NA_INTERVAL 60
/* Set the data packet period */
#define SDN_CONF_DATA_PACKET_INTERVAL 40
/* Linkaddr size */
#define LINKADDR_CONF_SIZE 2
#define IEEE_ADDR_CONF_ADDRESS \
    {                          \
        0x00, 0x12             \
    }
/* Num of max routing routes */
#define SDN_CONF_MAX_ROUTES 30
#define NBR_TABLE_CONF_MAX_NEIGHBORS 10
/* SDN STATISTICS? */
#define SDN_STATISTICS 0
/* Max number of neighbors in cache */
#define SDN_DS_NBR_CONF_MAX_NEIGHBOR_CACHES 10
#undef NETSTACK_CONF_NETWORK
#define NETSTACK_CONF_NETWORK sdn_net_driver
#undef NETSTACK_CONF_ROUTING
#define NETSTACK_CONF_ROUTING sdn_routing_driver

/* Set to enable TSCH security */
#ifndef WITH_SECURITY
#define WITH_SECURITY 0
#endif /* WITH_SECURITY */

/*******************************************************/
/******************* Configure TSCH ********************/
/*******************************************************/
/* IEEE802.15.4 PANID */
#define IEEE802154_CONF_PANID 0x81a5

#define TSCH_PACKET_CONF_EACK_WITH_SRC_ADDR 1

/* Do not start TSCH at init, wait for NETSTACK_MAC.on() */
#define TSCH_CONF_AUTOSTART 0

#ifdef CONTIKI_TARGET_SIMPLELINK
#define QUEUEBUF_CONF_NUM 8
#else
#define QUEUEBUF_CONF_NUM 128
#endif

#if BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED || BUILD_WITH_SDN_ORCHESTRA
#define TSCH_CALLBACK_PACKET_READY orchestra_callback_packet_ready
#define TSCH_CALLBACK_NEW_TIME_SOURCE orchestra_callback_new_time_source
#define NETSTACK_CONF_ROUTING_NEIGHBOR_ADDED_CALLBACK orchestra_callback_child_added
#define NETSTACK_CONF_SDN_RANK_UPDATED_CALLBACK orchestra_callback_rank_updated
#if BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED
#define NETSTACK_CONF_SDN_SA_LINK_CALLBACK orchestra_callback_add_sa_link
#define NETSTACK_CONF_SDN_SLOTFRAME_SIZE_CALLBACK orchestra_callback_slotframe_size
#define NETSTACK_CONF_SDN_PACKET_TX_FAILED orchestra_callback_packet_transmission_failed
#endif
#define NETSTACK_CONF_ROUTING_NEIGHBOR_REMOVED_CALLBACK orchestra_callback_child_removed
#define TSCH_CALLBACK_ROOT_NODE_UPDATED orchestra_callback_root_node_updated
#endif /* BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED || BUILD_WITH_SDN_ORCHESTRA */

#if BUILD_WITH_SDN_ORCHESTRA
#define ORCHESTRA_CONF_UNICAST_PERIOD 10 // This is the number of sensor nodes
#endif

#if WITH_SECURITY

/* Enable security */
#define LLSEC802154_CONF_ENABLED 1

#endif /* WITH_SECURITY */

/* Enable printing of packet counters */
#define LINK_STATS_CONF_PACKET_COUNTERS 0

/* Logs */
/* Logging */
#define LOG_CONF_LEVEL_RPL LOG_LEVEL_NONE
#define LOG_CONF_LEVEL_TCPIP LOG_LEVEL_NONE
#define LOG_CONF_LEVEL_IPV6 LOG_LEVEL_NONE
#define LOG_CONF_LEVEL_6LOWPAN LOG_LEVEL_NONE
#define LOG_CONF_LEVEL_MAC LOG_LEVEL_ERR
/* Do not enable LOG_CONF_LEVEL_FRAMER on SimpleLink,
   that will cause it to print from an interrupt context. */
#ifndef CONTIKI_TARGET_SIMPLELINK
#define LOG_CONF_LEVEL_FRAMER LOG_LEVEL_ERR
#endif
#define TSCH_LOG_CONF_PER_SLOT 0
/* Logging for the SDWSN netstack */
#define LOG_CONF_LEVEL_SDWSN LOG_LEVEL_ERR
#define LOG_CONF_LEVEL_NA LOG_LEVEL_ERR
#define LOG_CONF_LEVEL_DATA LOG_LEVEL_ERR
#define LOG_CONF_LEVEL_NBR_DS LOG_LEVEL_ERR
#define LOG_CONF_LEVEL_ROUTE_DS LOG_LEVEL_ERR
#define LOG_CONF_LEVEL_ND LOG_LEVEL_ERR
#define LOG_CONF_LEVEL_SDN_NET LOG_LEVEL_ERR
#define LOG_CONF_LEVEL_RA LOG_LEVEL_ERR
#define LOG_CONF_LEVEL_SA LOG_LEVEL_ERR
#define LOG_CONF_LEVEL_SDN LOG_LEVEL_ERR
#define LOG_CONF_LEVEL_SDN_POWER LOG_LEVEL_ERR
#define LOG_CONF_LEVEL_SDN_ORCHESTRA LOG_LEVEL_ERR
#define LOG_CONF_LEVEL_SDN_ORCHESTRA_UC LOG_LEVEL_ERR
/*---------------------------------------------------------------------------*/
#endif /* PROJECT_CONF_H_ */
