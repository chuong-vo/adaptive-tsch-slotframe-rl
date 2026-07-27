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

#ifndef SDNBUF_H_
#define SDNBUF_H_

#include "contiki.h"
#include "net/sdn-net/sd-wsn.h"
#include "stdbool.h"

/**
 * This is the default value of MAC-layer transmissons for uIPv6
 *
 * It means that the limit is selected by the MAC protocol instead of uIPv6.
 */
#define SDN_MAX_MAC_TRANSMISSIONS_UNDEFINED 0

/* MAC will set the default for this packet */
#define SDNBUF_ATTR_LLSEC_LEVEL_MAC_DEFAULT 0xffff

/**
 * \brief          Resets uIP buffer
 */
void sdnbuf_clear(void);

/**
 * \brief          Set the length of the uIP buffer
 * \param len      The new length
 * \retval         true if the len was successfully set, false otherwise
 */
bool sdnbuf_set_len(uint16_t len);

/**
 * \brief          Updates the length field in the uIP buffer
 * \param hdr      The header
 * \param len      The new length value
 */
void sdnbuf_set_len_field(struct sdn_ip_hdr *hdr, uint16_t len);

/**
 * \brief          Returns the value of the length field in the uIP buffer
 * \param hdr      The header
 * \retval         The length value
 */
uint8_t sdnbuf_get_len_field(struct sdn_ip_hdr *hdr);
/**
 * \brief          Returns the value of the length field in the SDN_IP buffer
 * \param hdr      The header
 * \retval         The length value
 */
uint8_t nabuf_get_len_field(struct sdn_na_hdr *hdr);

/**
 * \brief          Returns the value of the length field in the NC buffer
 * \param hdr      The header
 * \retval         The length value
 */
uint8_t ncbuf_get_len_field(struct sdn_ra_hdr *hdr);

/**
 * \brief          Returns the value of the length field in the SR buffer
 * \param hdr      The header
 * \retval         The length value
 */
uint8_t srbuf_get_len_field(struct sdn_sa_hdr *hdr);

/**
 * \brief          Get the next IPv6 header.
 * \param buffer   A pointer to the buffer holding the IPv6 packet
 * \param size     The size of the data in the buffer
 * \param protocol A pointer to a variable where the protocol of the header will be stored
 * \retval         returns address of the next header, or NULL in case of insufficient buffer space
 *
 *                 This function moves to the next header in a IPv6 packet.
 */
uint8_t *sdnbuf_get_next_header(uint8_t *buffer, uint16_t size, uint8_t *protocol);
/**
 * \brief          Get the value of the attribute
 * \param type     The attribute to get the value of
 * \retval         The value of the attribute
 *
 *                 This function gets the value of a specific sdnbuf attribute.
 */
uint16_t sdnbuf_get_attr(uint8_t type);

/**
 * \brief          Set the value of the attribute
 * \param type     The attribute to set the value of
 * \param value    The value to set
 * \retval         0 - indicates failure of setting the value
 * \retval         1 - indicates success of setting the value
 *
 *                 This function sets the value of a specific sdnbuf attribute.
 */
int sdnbuf_set_attr(uint8_t type, uint16_t value);

/**
 * \brief          Set the default value of the attribute
 * \param type     The attribute to set the default value of
 * \param value    The value to set
 * \retval         0 - indicates failure of setting the value
 * \retval         1 - indicates success of setting the value
 *
 *                 This function sets the default value of a uipbuf attribute.
 */
int sdnbuf_set_default_attr(uint8_t type, uint16_t value);

/**
 * \brief          Clear all attributes.
 *
 *                 This function clear all attributes in the uipbuf attributes
 *                 including all flags.
 */
void sdnbuf_clear_attr(void);

void sdnbuf_init(void);

/**
 * \brief The attributes defined for uipbuf attributes function.
 *
 */
enum
{
  SDNBUF_ATTR_LLSEC_LEVEL,           /**< Control link layer security level. */
  SDNBUF_ATTR_LLSEC_KEY_ID,          /**< Control link layer security key ID. */
  SDNBUF_ATTR_INTERFACE_ID,          /**< The interface to output packet on */
  SDNBUF_ATTR_PHYSICAL_NETWORK_ID,   /**< Physical network ID (mapped to PAN ID)*/
  SDNBUF_ATTR_MAX_MAC_TRANSMISSIONS, /**< MAX transmissions of the packet MAC */
  // UIPBUF_ATTR_FLAGS,   /**< Flags that can control lower layers.  see above. */
  SDNBUF_ATTR_MAX
};

#endif