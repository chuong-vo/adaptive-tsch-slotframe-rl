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

#include "sdnbuf.h"
#include <string.h>
/*---------------------------------------------------------------------------*/

static uint16_t sdnbuf_attrs[SDNBUF_ATTR_MAX];
static uint16_t sdnbuf_default_attrs[SDNBUF_ATTR_MAX];

/*---------------------------------------------------------------------------*/
void sdnbuf_clear(void)
{
  sdn_len = 0;
  sdnbuf_clear_attr();
}
/*---------------------------------------------------------------------------*/
bool sdnbuf_set_len(uint16_t len)
{
  if (len <= SDN_LINK_MTU)
  {
    sdn_len = len;
    return true;
  }
  else
  {
    return false;
  }
}
/*---------------------------------------------------------------------------*/
uint8_t *sdnbuf_get_next_header(uint8_t *buffer, uint16_t size, uint8_t *protocol)
{
  int curr_hdr_len = 0;
  int next_hdr_len = 0;
  uint8_t *next_header = NULL;
  struct sdn_ip_hdr *sdnbuf = NULL;

  /* protocol in the IP buffer */
  sdnbuf = (struct sdn_ip_hdr *)buffer;
  *protocol = sdnbuf->vap & 0x0F;
  curr_hdr_len = SDN_IPH_LEN;

  /* Check first if enough space for current header */
  if (curr_hdr_len > size)
  {
    return NULL;
  }

  if (*protocol == SDN_PROTO_ND)
  {
    next_hdr_len = SDN_NDH_LEN;
  }
  else if (*protocol == SDN_PROTO_NA)
  {
    next_hdr_len = SDN_NAH_LEN;
  }
  else if (*protocol == SDN_PROTO_RA)
  {
    next_hdr_len = SDN_RAH_LEN;
  }
  else if (*protocol == SDN_PROTO_SA)
  {
    next_hdr_len = SDN_SAH_LEN;
  }
  else if (*protocol == SDN_PROTO_DATA)
  {
    next_hdr_len = SDN_DATA_LEN;
  }

  next_header = buffer + curr_hdr_len;

  /* Size must be enough to hold both the current and next header */
  if (next_hdr_len == 0 || curr_hdr_len + next_hdr_len > size)
  {
    return NULL;
  }
  return next_header;
}
/*---------------------------------------------------------------------------*/
void sdnbuf_set_len_field(struct sdn_ip_hdr *hdr, uint16_t len)
{
  hdr->tlen = len;
  //hdr->len[0] = (len >> 8);
  //hdr->len[1] = (len & 0xff);
}
/*---------------------------------------------------------------------------*/
uint8_t
sdnbuf_get_len_field(struct sdn_ip_hdr *hdr)
{
  return hdr->tlen;
  // return ((uint16_t)(hdr->len[0]) << 8) + hdr->len[1];
}
/*---------------------------------------------------------------------------*/
uint8_t nabuf_get_len_field(struct sdn_na_hdr *hdr)
{
  return hdr->payload_len;
  // return ((uint16_t)(hdr->len[0]) << 8) + hdr->len[1];
}
/*---------------------------------------------------------------------------*/
uint8_t ncbuf_get_len_field(struct sdn_ra_hdr *hdr)
{
  return hdr->payload_len;
  // return ((uint16_t)(hdr->len[0]) << 8) + hdr->len[1];
}
/*---------------------------------------------------------------------------*/
uint8_t srbuf_get_len_field(struct sdn_sa_hdr *hdr)
{
  return hdr->payload_len;
  // return ((uint16_t)(hdr->len[0]) << 8) + hdr->len[1];
}
/*---------------------------------------------------------------------------*/
uint16_t sdnbuf_get_attr(uint8_t type)
{
  if (type < SDNBUF_ATTR_MAX)
  {
    return sdnbuf_attrs[type];
  }
  return 0;
}
/*---------------------------------------------------------------------------*/
int sdnbuf_set_attr(uint8_t type, uint16_t value)
{
  if (type < SDNBUF_ATTR_MAX)
  {
    sdnbuf_attrs[type] = value;
    return 1;
  }
  return 0;
}
/*---------------------------------------------------------------------------*/
int sdnbuf_set_default_attr(uint8_t type, uint16_t value)
{
  if (type < SDNBUF_ATTR_MAX)
  {
    sdnbuf_default_attrs[type] = value;
    return 1;
  }
  return 0;
}
/*---------------------------------------------------------------------------*/
void sdnbuf_clear_attr(void)
{
  /* set everything to "defaults" */
  memcpy(sdnbuf_attrs, sdnbuf_default_attrs, sizeof(sdnbuf_attrs));
}
/*---------------------------------------------------------------------------*/
void sdnbuf_init(void)
{
  memset(sdnbuf_default_attrs, 0, sizeof(sdnbuf_default_attrs));
  /* And initialize anything that should be initialized */
  sdnbuf_set_default_attr(SDNBUF_ATTR_MAX_MAC_TRANSMISSIONS,
                          SDN_MAX_MAC_TRANSMISSIONS_UNDEFINED);
  /* set the not-set default value - this will cause the MAC layer to
     configure its default */
  sdnbuf_set_default_attr(SDNBUF_ATTR_LLSEC_LEVEL,
                          SDNBUF_ATTR_LLSEC_LEVEL_MAC_DEFAULT);
}

/*---------------------------------------------------------------------------*/
