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
 * \addtogroup sdn-serial
 * @{
 *
 * @file sdn-serial.h
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief SDN serial interface header
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#ifndef SDN_SERIAL_H
#define SDN_SERIAL_H

#include "contiki.h"
#include "linkaddr.h"
#include "lib/ringbuf.h"

/* HDLC Asynchronous framing */
/* The frame boundary octet is 01111110, (7E in hexadecimal notation) */
#define FRAME_BOUNDARY_OCTET 0x7E

/* A "control escape octet", has the bit sequence '01111101', (7D hexadecimal) */
#define CONTROL_ESCAPE_OCTET 0x7D

/* If either of these two octets appears in the transmitted data, an escape octet is sent, */
/* followed by the original data octet with bit 5 inverted */
#define INVERT_OCTET 0x20

/* Ringbuffer for inconming and outgoing interfaces */
#ifndef SDN_SERIAL_CONF_BUFFER_SIZE
#define SDN_SERIAL_BUFSIZE 128 /* 1,2,4,8,16,32,64,128 or 256 bytes */
#else                          /* UIP_CONF_BUFFER_SIZE */
#define SDN_SERIAL_BUFSIZE (SDN_SERIAL_CONF_BUFFER_SIZE)
#endif /* UIP_CONF_BUFFER_SIZE */

/* Serial packet buffer */
#ifndef SDN_SERIAL_PACKET_CONF_BUFFER_SIZE
#define SDN_SERIAL_PACKET_BUFFER_SIZE 128
#else /* UIP_CONF_BUFFER_SIZE */
#define SDN_SERIAL_PACKET_BUFFER_SIZE (SDN_SERIAL_PACKET_CONF_BUFFER_SIZE)
#endif /* UIP_CONF_BUFFER_SIZE */

/* Header size */
#define SDN_SERIAL_PACKETH_LEN 8      /* Size of the sdn serial packet header */
#define SDN_SERIAL_PACKET_NODEH_LEN 8 /* Size of the sdn serial node packet header */

#define SDN_SERIAL_MAX_PACKET_SIZE (SDN_SERIAL_PACKET_BUFFER_SIZE - SDN_SERIAL_PACKETH_LEN)

/**
 * Direct access to SDN serial packet header and payload
 */
#define SDN_SERIAL_PACKET_BUF ((struct sdn_serial_packet_hdr *)sdn_serial_packet_buf)
#define SDN_SERIAL_PACKET_PAYLOAD_BUF(ext) ((unsigned char *)sdn_serial_packet_buf + SDN_SERIAL_PACKETH_LEN + (ext))

/* Define types of messages */
#define SDN_SERIAL_MSG_TYPE_EMPTY 1
#define SDN_SERIAL_MSG_TYPE_CP 2 // Sensor node information
#define SDN_SERIAL_MSG_TYPE_DP 3 // Sensor data packet
#define SDN_SERIAL_MSG_TYPE_ACK 4 // Sensor data packet
// #define SDN_SERIAL_MSG_TYPE_NBR 3   // Sensor node neighbors, rssi and rank

/* SDN serail packet header */
struct sdn_serial_packet_hdr
{
    linkaddr_t addr;
    int16_t pkt_chksum;
    uint8_t type;
    uint8_t payload_len;
    uint8_t reserved[2];
};

/**
 * The SDN serial packet buffer.
 *
 * The sdn_serial_aligned_buf array is used to hold incoming and outgoing
 * packets. The device driver should place incoming data into this
 * buffer. When sending data, the device driver should read the
 * outgoing data from this buffer.
*/
typedef union
{
    uint32_t u32[(SDN_SERIAL_PACKET_BUFFER_SIZE + 3) / 4];
    uint8_t u8[SDN_SERIAL_PACKET_BUFFER_SIZE];
} sdn_serial_packet_buf_t;

extern sdn_serial_packet_buf_t sdn_serial_aligned_buf;

/** Macro to access sdn_serial_aligned_buf as an array of bytes */
#define sdn_serial_packet_buf (sdn_serial_aligned_buf.u8)

extern process_event_t sdn_serial_raw_binary_packet_ev;
extern process_event_t sdn_serial_ev;

/**
 * The length of the packet in the sdn_serial_buf buffer.
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
extern uint16_t sdn_serial_len;

/**
 * Get one byte of input from the serial driver.
 *
 * This function is to be called from the actual RS232 driver to get
 * one byte of serial data input.
 *
 * For systems using low-power CPU modes, the return value of the
 * function can be used to determine if the CPU should be woken up or
 * not. If the function returns non-zero, the CPU should be powered
 * up. If the function returns zero, the CPU can continue to be
 * powered down.
 *
 * \param c The data that is received.
 *
 * \return Non-zero if the CPU should be powered up, zero otherwise.
 */

int sdn_serial_input_byte(unsigned char c);

/* Callback typedef for the serial send char */
typedef int (*sdn_serial_send_char)(int);

void sdn_serial_init(sdn_serial_send_char callback);

/* Send serial packet through serial interface
    It will send whatever is in the SDN_SERIAL_BUFFER */
int sdn_serial_send(void);

/**
 * \brief          Returns the value of the length field in the SDN serial buffer
 * \param hdr      The serial packet header
 */
uint8_t sdn_serial_get_len(struct sdn_serial_packet_hdr *hdr);

PROCESS_NAME(sdn_serial_process);

#endif

/** @} */