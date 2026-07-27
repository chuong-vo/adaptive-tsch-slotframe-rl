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
 * @file sd-wsn.h
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief Header for the Contiki/SD-WSN interface
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#ifndef SD_WSN_H_
#define SD_WSN_H_

#include "net/netstack.h"
/* Header sizes. */
#define SDN_IPH_LEN sizeof(struct sdn_ip_hdr)

#define SDN_NDH_LEN 6  /* Size of neighbor discovery header */
#define SDN_NAH_LEN 10 /* Size of neighbor advertisement packet header */
#define SDN_NAPL_LEN 6 /* Size of neighbor advertisement payload size */
#define SDN_RAH_LEN 6  /* Size of network configuration routing and schedules packet header */
#define SDN_RAPL_LEN 6 /* Size of RA payload */
#define SDN_SAH_LEN 6  /* Size of Schedule advertisement (SA) header */
#define SDN_SAPL_LEN 8 /* Size of SA payload */
// #define SDN_DATAH_LEN 1 /* Size of data header*/
#define SDN_DATA_LEN 11 /* Size of data packet */

// #define sdn_l3_nd_hdr_len (SDN_IPH_LEN + SDN_NDH_LEN)
// #define sdn_l3_cp_hdr_len (SDN_IPH_LEN + SDN_CPH_LEN)

/**
 * Direct access to SDN IP header
 */
#define SDN_IP_BUF ((struct sdn_ip_hdr *)sdn_buf)
#define SDN_IP_PAYLOAD(ext) ((unsigned char *)sdn_buf + SDN_IPH_LEN + (ext))

/**
 * Direct access to SDN Data packets
 */
// #define SDN_DATA_HDR_BUF ((struct sdn_data_hdr *)SDN_IP_PAYLOAD(0))
// #define SDN_DATA_HDR_PAYLOAD(ext) ((unsigned char *)SDN_IP_PAYLOAD(0) + SDN_DATAH_LEN + (ext))

/**
 * Direct access to SDN Data packets
 */
#define SDN_DATA_BUF ((struct sdn_data *)SDN_IP_PAYLOAD(0))

/**
 * Direct access to neighbor discovery
 */
#define SDN_ND_BUF ((struct sdn_nd_hdr *)SDN_IP_PAYLOAD(0))
#define SDN_ND_PAYLOAD ((unsigned char *)SDN_IP_PAYLOAD(0) + SDN_NDH_LEN)

/**
 * Direct access to neighbor advertisement pkts
 */
#define SDN_NA_BUF ((struct sdn_na_hdr *)SDN_IP_PAYLOAD(0))
#define SDN_NA_PAYLOAD(ext) ((struct sdn_na_payload *)(SDN_IP_PAYLOAD(0) + SDN_NAH_LEN) + (ext))

/**
 * Direct access to Routes Advertisement (RA) packet
 */
#define SDN_RA_BUF ((struct sdn_ra_hdr *)SDN_IP_PAYLOAD(0))
#define SDN_RA_PAYLOAD(ext) ((struct sdn_ra_payload *)(SDN_IP_PAYLOAD(0) + SDN_RAH_LEN) + (ext))

/**
 * Direct access to Schedules Advertisement (SA) packet
 */
#define SDN_SA_BUF ((struct sdn_sa_hdr *)SDN_IP_PAYLOAD(0))
#define SDN_SA_PAYLOAD(ext) ((struct sdn_sa_payload *)(SDN_IP_PAYLOAD(0) + SDN_SAH_LEN) + (ext))

/**
 * The size of the SDN packet buffer.
 *
 * The uIP packet buffer should not be smaller than 60 bytes, and does
 * not need to be larger than 1514 bytes. Lower size results in lower
 * TCP throughput, larger size results in higher TCP throughput.
 *
 * \hideinitializer
 */
/** The maximum transmission unit at the IP Layer*/
#define SDN_LINK_MTU 1000

#ifndef SDN_CONF_BUFFER_SIZE
#define SDN_BUFSIZE 600
#else /* UIP_CONF_BUFFER_SIZE */
#define SDN_BUFSIZE (SDN_CONF_BUFFER_SIZE)
#endif /* UIP_CONF_BUFFER_SIZE */

/** \brief General DS6 definitions */
/** Period for uip-ds6 periodic task*/
#ifndef SDN_DS_CONF_PERIOD
#define SDN_DS_PERIOD (CLOCK_SECOND / 10)
#else
#define SDN_DS_PERIOD SDN_DS_CONF_PERIOD
#endif

/**
 * Construct an IP address from four bytes.
 *
 * This function constructs an IP address of the type that uIP handles
 * internally from four bytes. The function is handy for specifying IP
 * addresses to use with e.g. the uip_connect() function.
 *
 * Example:
 \code
 uip_ipaddr_t ipaddr;
 struct uip_conn *c;

 uip_ipaddr(&ipaddr, 192,168,1,2);
 c = uip_connect(&ipaddr, UIP_HTONS(80));
 \endcode
 *
 * \param addr A pointer to a uip_ipaddr_t variable that will be
 * filled in with the IP address.
 *
 * \param addr0 The first octet of the IP address.
 * \param addr1 The second octet of the IP address.
 *
 * \hideinitializer
 */
#define sdn_addr(addr, addr0, addr1) \
    do                               \
    {                                \
        (addr)->u8[0] = addr0;       \
        (addr)->u8[1] = addr1;       \
                                     \
    } while (0)
/** \brief set IP address a to the link local all-nodes multicast address */
#define sdn_create_broadcast_addr(a) sdn_addr(a, 0xFF, 0xFF)

/**
 * The SDN packet buffer.
 *
 * The sdn_aligned_buf array is used to hold incoming and outgoing
 * packets. The device driver should place incoming data into this
 * buffer. When sending data, the device driver should read the
 * outgoing data from this buffer.
 */

typedef union
{
    uint32_t u32[(SDN_BUFSIZE + 3) / 4];
    uint8_t u8[SDN_BUFSIZE];
} sdn_buf_t;

extern sdn_buf_t sdn_aligned_buf;

/** Macro to access uip_aligned_buf as an array of bytes */
#define sdn_buf (sdn_aligned_buf.u8)

/**
 * Convert 16-bit quantity from host byte order to network byte order.
 *
 * This macro is primarily used for converting constants from host
 * byte order to network byte order. For converting variables to
 * network byte order, use the uip_htons() function instead.
 *
 * \hideinitializer
 */
// #ifndef UIP_HTONS
// #if UIP_BYTE_ORDER == UIP_BIG_ENDIAN
// #define UIP_HTONS(n) (n)
// #define UIP_HTONL(n) (n)
// #else /* UIP_BYTE_ORDER == UIP_BIG_ENDIAN */
// #define UIP_HTONS(n) (uint16_t)((((uint16_t)(n)) << 8) | (((uint16_t)(n)) >> 8))
// #define UIP_HTONL(n) (((uint32_t)UIP_HTONS(n) << 16) | UIP_HTONS((uint32_t)(n) >> 16))
// #endif /* UIP_BYTE_ORDER == UIP_BIG_ENDIAN */
// #else
// #error "UIP_HTONS already defined!"
// #endif /* UIP_HTONS */

/**
 * Convert a 16-bit quantity from host byte order to network byte order.
 *
 * This function is primarily used for converting variables from host
 * byte order to network byte order. For converting constants to
 * network byte order, use the UIP_HTONS() macro instead.
 */
#ifndef sdnip_htons
uint16_t sdnip_htons(uint16_t val);
#endif /* uip_htons */
#ifndef sdn_ntohs
#define sdn_ntohs sdnip_htons
#endif

#ifndef sdnip_htonl
uint32_t sdnip_htonl(uint32_t val);
#endif /* uip_htonl */
#ifndef sdnip_ntohl
#define sdnip_ntohl sdnip_htonl
#endif

/**
 * The length of the packet in the uip_buf buffer.
 *
 * The global variable uip_len holds the length of the packet in the
 * uip_buf buffer.
 *
 * When the network device driver calls the uIP input function,
 * uip_len should be set to the length of the packet in the uip_buf
 * buffer.
 *
 * When sending packets, the device driver should use the contents of
 * the uip_len variable to determine the length of the outgoing
 * packet.
 *
 */
extern uint16_t sdn_len;
/**
 * Pointer to the application data in the packet buffer.
 *
 * This pointer points to the application data when the application is
 * called. If the application wishes to send data, the application may
 * use this space to write the data into before calling uip_send().
 */
extern void *sdn_appdata;

/** The final protocol after IPv6 extension headers:
 * UIP_PROTO_TCP, UIP_PROTO_UDP or UIP_PROTO_ICMP6 */
extern uint8_t sdn_last_proto;

/**
 * The uIP TCP/IP statistics.
 *
 * This is the variable in which the uIP TCP/IP statistics are gathered.
 */
#if SDN_STATISTICS == 1
extern struct sdn_stats sdn_stat;
#define SDN_STAT(s) s
#else
#define SDN_STAT(s)
#endif /* UIP_STATISTICS == 1 */

/**
 * The structure holding the TCP/IP statistics that are gathered if
 * UIP_STATISTICS is set to 1.
 *
 */
struct sdn_stats
{
    struct
    {
        uip_stats_t recv;     /**< Number of received packets at the IP layer. */
        uip_stats_t sent;     /**< Number of sent packets at the IP layer. */
        uint32_t forwarded;   /**< Number of forwarded packets at the IP layer. */
        uip_stats_t drop;     /**< Number of dropped packets at the IP layer. */
        uip_stats_t vhlerr;   /**< Number of packets dropped due to wrong
                               IP version or header length. */
        uip_stats_t hblenerr; /**< Number of packets dropped due to wrong
                               IP length, high byte. */
        uip_stats_t lblenerr; /**< Number of packets dropped due to wrong
                               IP length, low byte. */
        uip_stats_t chkerr;   /**< Number of packets dropped due to IP
                               checksum errors. */
        uip_stats_t protoerr; /**< Number of packets dropped because they
                               were neither ICMP, UDP nor TCP. */
    } ip;                     /**< IP statistics. */
    struct
    {
        uip_stats_t recv;    /**< Number of received ND packets. */
        uint32_t sent;       /**< Number of sent ND packets. */
        uint32_t sent_bytes; /**< Number of sent ND bytes. */
        uip_stats_t drop;    /**< Number of dropped ND packets. */
        uip_stats_t typeerr; /**< Number of ND packets with a wrong type. */
        uip_stats_t chkerr;  /**< Number of ND packets with a bad checksum. */
    } nd;                    /**< Neighbor discovery statistics. */
    struct
    {
        uint32_t adv;       /**< Number of sent neighbor advertisement segments. */
        uint32_t adv_bytes; /**< Number of sent neighbor advertisement bytes. */
        uint32_t nc;        /**< Number of sent network configuration segments. */
        uint32_t nc_bytes;  /**< Number of sent network configuration bytes. */
    } cp;                   /**< Control statistics. */
    struct
    {
        uint32_t sent_agg;        /**< Number of sent data segments with aggregation. */
        uint32_t sent_agg_bytes;  /**< Number of sent data bytes with aggregation. */
        uint32_t sent_nagg;       /**< Number of sent data segments without aggregation. */
        uint32_t sent_nagg_bytes; /**< Number of sent data bytes without aggregation. */
    } data;                       /**< Data statistics. */
    struct
    {
        uint32_t dead; /**< Number of dead nodes. */
    } nodes;           /**< Nodes statistics. */
};

void sdn_wsn_init(void);

/**
 * Process an incoming packet.
 *
 * This function should be called when the device driver has received
 * a packet from the network. The packet from the device driver must
 * be present in the uip_buf buffer, and the length of the packet
 * should be placed in the uip_len variable.
 *
 * When the function returns, there may be an outbound packet placed
 * in the uip_buf packet buffer. If so, the uip_len variable is set to
 * the length of the packet. If no packet is to be sent out, the
 * uip_len variable is set to 0.
 *
 * The usual way of calling the function is presented by the source
 * code below.
 \code
 uip_len = devicedriver_poll();
 if(uip_len > 0) {
 uip_input();
 if(uip_len > 0) {
 devicedriver_send();
 }
 }
 \endcode
 *
 * \note If you are writing a uIP device driver that needs ARP
 * (Address Resolution Protocol), e.g., when running uIP over
 * Ethernet, you will need to call the uIP ARP code before calling
 * this function:
 \code
 #define BUF ((struct uip_eth_hdr *)&uip_buf[0])
 uip_len = ethernet_devicedrver_poll();
 if(uip_len > 0) {
 if(BUF->type == UIP_HTONS(UIP_ETHTYPE_IP)) {
 uip_arp_ipin();
 uip_input();
 if(uip_len > 0) {
 uip_arp_out();
 ethernet_devicedriver_send();
 }
 } else if(BUF->type == UIP_HTONS(UIP_ETHTYPE_ARP)) {
 uip_arp_arpin();
 if(uip_len > 0) {
 ethernet_devicedriver_send();
 }
 }
 \endcode
 *
 * \hideinitializer
 */
#define sdn_input() sdnip_process(UIP_DATA)

/*---------------------------------------------------------------------------*/
/* All the stuff below this point is internal to uIP and should not be
 * used directly by an application or by a device driver.
 */
/*---------------------------------------------------------------------------*/

/* uip_process(flag):
 *
 * The actual uIP function which does all the work.
 */
void sdnip_process(uint8_t flag);

/* The following flags are passed as an argument to the uip_process()
   function. They are used to distinguish between the two cases where
   uip_process() is called. It can be called either because we have
   incoming data that should be processed, or because the periodic
   timer has fired. These values are never used directly, but only in
   the macros defined in this file. */

#define UIP_DATA 1 /* Tells uIP that there is incoming    \ \ \
                      data in the uip_buf buffer. The     \ \ \
                      length of the data is stored in the \ \ \
                      global variable uip_len. */
// #define UIP_TIMER         2     /* Tells uIP that the periodic timer
//                                    has fired. */
// #define UIP_POLL_REQUEST  3     /* Tells uIP that a connection should
//                                    be polled. */
// #define UIP_UDP_SEND_CONN 4     /* Tells uIP that a UDP datagram
//    should be constructed in the
//    uip_buf buffer. */

void sdn_ip_process(uint8_t flag);

/* The following flags are passed as an argument to the uip_process()
   function. They are used to distinguish between the two cases where
   uip_process() is called. It can be called either because we have
   incoming data that should be processed, or because the periodic
   timer has fired. These values are never used directly, but only in
   the macros defined in this file. */

#define SDN_IP_DATA 1  /* Tells uIP that there is incoming \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \
                       data in the uip_buf buffer. The     \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \
                       length of the data is stored in the \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \
                       global variable uip_len. */
#define SDN_IP_TIMER 2 /* Tells uIP that the periodic timer \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \ \
                       has fired. */

/* The SDN header */

struct sdn_ip_hdr
{
    /* SDN IP header */
    uint8_t vap,
        tlen,
        ttl;
    int16_t hdr_chksum;
    linkaddr_t scr, dest;
};

// struct sdn_data_hdr
// {
//     uint8_t len;
// };

struct sdn_data
{
    uint16_t cycle_seq;
    uint8_t seq;
    uint8_t temp,
        humidity,
        light;
    uint16_t asn_ls4b_lsb,
        asn_ls4b_msb;
    uint8_t asn_ms1b;
};

/* The ND headers. */
struct sdn_nd_hdr
{
    int16_t rank, rssi;
    int16_t ndchksum;
};

/* NA message structure */
struct sdn_na_hdr
{
    uint8_t payload_len,
        rank;
    uint16_t energy,
        cycle_seq;
    uint8_t seq,
        padding;
    int16_t pkt_chksum;
};

/* NA payload structure */
struct sdn_na_payload
{
    linkaddr_t nb_addr;
    int16_t rssi;
    uint16_t etx;
};

/* NC message structure for routes */
struct sdn_ra_hdr
{
    uint8_t payload_len,
        padding;
    uint16_t seq,
        pkt_chksum;
};

/* NC payload structure for routes */
struct sdn_ra_payload
{
    linkaddr_t scr,
        dest,
        via;
};

/* NC message structure for schedules */
struct sdn_sa_hdr
{
    uint8_t payload_len,
        sf_len;
    uint16_t seq,
        pkt_chksum;
};

/* NC message structure for schedules */
struct sdn_sa_payload
{
    uint8_t type,
        channel_offset,
        time_offset,
        padding;
    linkaddr_t scr, dst;
};

/**
 * The buffer size available for user data in the \ref uip_buf buffer.
 *
 * This macro holds the available size for user data in the \ref
 * uip_buf buffer. The macro is intended to be used for checking
 * bounds of available user data.
 *
 * Example:
 \code
 snprintf(uip_appdata, UIP_APPDATA_SIZE, "%u\n", i);
 \endcode
 *
 * \hideinitializer
 */
#define SDN_APPDATA_SIZE (SDN_BUFSIZE - SDN_IPH_LEN)

#define SDN_PROTO_ND 1
#define SDN_PROTO_NA 2   /* Neighbor advertisement */
#define SDN_PROTO_RA 3   /* Routes Advertisement */
#define SDN_PROTO_SA 4   /* Schedule Advertisment */
#define SDN_PROTO_DATA 5 /* Data packet */

/**
 * Calculate the Internet checksum over a buffer.
 *
 * The Internet checksum is the one's complement of the one's
 * complement sum of all 16-bit words in the buffer.
 *
 * See RFC1071.
 *
 * \param data A pointer to the buffer over which the checksum is to be
 * computed.
 *
 * \param len The length of the buffer over which the checksum is to
 * be computed.
 *
 * \return The Internet checksum of the buffer.
 */
uint16_t sdn_chksum(uint16_t *data, uint16_t len);

/**
 * Calculate the IP header checksum of the packet header in uip_buf.
 *
 * The IP header checksum is the Internet checksum of the 20 bytes of
 * the IP header.
 *
 * \return The IP header checksum of the IP header in the uip_buf
 * buffer.
 */
uint16_t sdn_ipchksum(void);
/**
 * Calculate the ICMP checksum of the packet in uip_buf.
 *
 * \return The ICMP checksum of the ICMP packet in uip_buf
 */
uint16_t sdn_ndchksum(void);
/**
 * Calculate the checksum of the entire NA packet.
 *
 * \return The checksum of the NA packet in uip_buf
 */
uint16_t sdn_nachksum(uint8_t len);
/**
 * Calculate the checksum of the entire RA packet.
 *
 * \return The checksum of the RA packet in uip_buf
 */
uint16_t sdn_rachksum(uint8_t len);

/** \brief Periodic processing of data structures */
extern struct etimer sdn_ds_timer_periodic;
void sdn_ds_periodic(void);

void print_buff(uint8_t *buf, size_t buflen, int8_t bare);

#endif

/** @} */
