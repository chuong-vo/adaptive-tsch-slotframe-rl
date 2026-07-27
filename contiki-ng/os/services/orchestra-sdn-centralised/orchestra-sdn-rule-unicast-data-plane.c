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
 * @file orchestra-sdn-rule-unicast-data-plane.c
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief Orchestra data plane
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#include "contiki.h"
#include "orchestra.h"
#include "net/packetbuf.h"
#include "net/mac/tsch/tsch.h"
#include "net/queuebuf.h"
#include <inttypes.h>

/* Log configuration */
/* Log configuration */
#include "sys/log.h"
#define LOG_MODULE "SDN-Orchestra-UC"
#if LOG_CONF_LEVEL_SDN_ORCHESTRA_UC
#define LOG_LEVEL LOG_CONF_LEVEL_SDN_ORCHESTRA_UC
#else
#define LOG_LEVEL LOG_LEVEL_NONE
#endif /* LOG_CONF_LEVEL_SDN_ORCHESTRA_UC */

static uint16_t slotframe_handle = 0;
static uint16_t current_seq = 0;
static struct tsch_slotframe *sf_unicast;

static int get_ts_ch_from_dst_addr(const linkaddr_t *dst, uint16_t *timeslot, uint16_t *channel_offset);

/*---------------------------------------------------------------------------*/
static uint16_t
get_node_timeslot(const linkaddr_t *addr)
{
  if (addr != NULL && ORCHESTRA_UNICAST_PERIOD > 0)
  {
    return ORCHESTRA_LINKADDR_HASH(addr) % ORCHESTRA_UNICAST_PERIOD;
  }
  else
  {
    return 0xffff;
  }
}
/*---------------------------------------------------------------------------*/
static uint16_t
get_node_channel_offset(const linkaddr_t *addr)
{
  if (addr != NULL && ORCHESTRA_UNICAST_MAX_CHANNEL_OFFSET >= ORCHESTRA_UNICAST_MIN_CHANNEL_OFFSET)
  {
    return ORCHESTRA_LINKADDR_HASH(addr) % (ORCHESTRA_UNICAST_MAX_CHANNEL_OFFSET - ORCHESTRA_UNICAST_MIN_CHANNEL_OFFSET + 1) + ORCHESTRA_UNICAST_MIN_CHANNEL_OFFSET;
  }
  else
  {
    return 0xffff;
  }
}
/*---------------------------------------------------------------------------*/
static void
child_added(const linkaddr_t *linkaddr)
{
}
/*---------------------------------------------------------------------------*/
static void
child_removed(const linkaddr_t *linkaddr)
{
}
/*---------------------------------------------------------------------------*/
#ifdef NETSTACK_CONF_SDN_PACKET_TX_FAILED
void orchestra_callback_packet_transmission_failed(struct tsch_neighbor *n,
                                                   struct tsch_packet *p,
                                                   struct tsch_link *link)
{
  int packet_attr_frametype = queuebuf_attr(p->qb, PACKETBUF_ATTR_FRAME_TYPE);
  if (packet_attr_frametype == FRAME802154_DATAFRAME && current_seq > 0)
  {
    LOG_WARN("Pkt tx failed\n");
    uint16_t timeslot, channel_offset;
    // Re-schedule the packet in the next closest and available UC link for neighbour
    get_ts_ch_from_dst_addr(&link->addr, &timeslot, &channel_offset);
    // int packet_attr_timeslot = queuebuf_attr(p->qb, PACKETBUF_ATTR_TSCH_TIMESLOT);
    // int packet_attr_channeloffset = queuebuf_attr(p->qb, PACKETBUF_ATTR_TSCH_CHANNEL_OFFSET);
    // PRINTF("Current ts %d ch %d\n", packet_attr_timeslot, packet_attr_channeloffset);
    queuebuf_set_attr(p->qb, PACKETBUF_ATTR_TSCH_TIMESLOT, timeslot);
    queuebuf_set_attr(p->qb, PACKETBUF_ATTR_TSCH_CHANNEL_OFFSET, channel_offset);
    // packet_attr_timeslot = queuebuf_attr(p->qb, PACKETBUF_ATTR_TSCH_TIMESLOT);
    // packet_attr_channeloffset = queuebuf_attr(p->qb, PACKETBUF_ATTR_TSCH_CHANNEL_OFFSET);
    // PRINTF("New current ts %d ch %d\n", packet_attr_timeslot, packet_attr_channeloffset);
  }
}
#endif /* NETSTACK_CONF_SDN_PACKET_TX_FAILED */
/*---------------------------------------------------------------------------*/
// static void remove_all_links()
// {
//   /* Remove all links belonging to this slotframe */
//   struct tsch_link *l;
//   while ((l = list_head(sf_unicast->links_list)))
//   {
//     tsch_schedule_remove_link(sf_unicast, l);
//   }
// }
/*---------------------------------------------------------------------------*/
static void
add_sa_link(uint8_t type, uint8_t channel_offset, uint8_t timeslot, linkaddr_t *addr)
{
  /* Remove all links in the slotframe if the rcv seq is greater that current seq */
  // if (seq > current_seq && sf_len != 0)
  // {
  //   remove_all_links();
  //   current_seq = seq;
  // }
  switch (type)
  {
  case LINK_OPTION_RX:
    tsch_schedule_add_link(sf_unicast,
                           LINK_OPTION_RX,
                           LINK_TYPE_NORMAL, &tsch_broadcast_address,
                           timeslot, channel_offset, 1);
    break;
  case LINK_OPTION_TX:
    tsch_schedule_add_link(sf_unicast,
                           LINK_OPTION_TX,
                           LINK_TYPE_NORMAL, addr,
                           timeslot, channel_offset, 1);
    break;

  default:
    break;
  }
}
/*---------------------------------------------------------------------------*/
static int
get_ts_ch_from_dst_addr(const linkaddr_t *dst, uint16_t *timeslot, uint16_t *channel_offset)
{
  /* We want to get the link which is the closest to the current ASN */
  uint16_t ts_asn = TSCH_ASN_MOD(tsch_current_asn, sf_unicast->size); // This is the timeslot of the current ASN
  LOG_INFO("tsch current .%" PRIx32 ", ts %d (%d.%d)\n", tsch_current_asn.ls4b, ts_asn, dst->u8[0], dst->u8[1]);
  int16_t difference, min = 127;
  uint16_t ts;
  struct tsch_link *l = list_head(sf_unicast->links_list);
  /* Loop over all items. Assume there is max one link per timeslot */
  while (l != NULL)
  {
    if (linkaddr_cmp(dst, &l->addr))
    {
      ts = l->timeslot;
      LOG_INFO("ts %d to dst %d.%d\n", ts, dst->u8[0], dst->u8[1]);
      // }
      difference = ts - ts_asn;
      LOG_INFO("difference %d\n", difference);
      if (difference < 0)
      {
        difference = difference + sf_unicast->size.val;
      }
      if (difference < min)
      {
        *timeslot = l->timeslot;
        *channel_offset = l->channel_offset;
        min = difference;
        LOG_INFO("min difference %d\n", min);
      }
    }
    l = list_item_next(l);
  }
  if (min == 127)
  {
    LOG_INFO("schedule not found %d\n", min);
    return 0;
  }
  else
  {
    LOG_INFO("schedule found %d (ts=%u)\n", min, *timeslot);
    return 1;
  }
}
/*---------------------------------------------------------------------------*/
static int
select_packet(uint16_t *slotframe, uint16_t *timeslot, uint16_t *channel_offset)
{
  /* Select data packets we have a unicast link to */
  const linkaddr_t *dest = packetbuf_addr(PACKETBUF_ADDR_RECEIVER);
  if (packetbuf_attr(PACKETBUF_ATTR_FRAME_TYPE) == FRAME802154_DATAFRAME && !linkaddr_cmp(dest, &linkaddr_null))
  {
    if (get_ts_ch_from_dst_addr(dest, timeslot, channel_offset))
    {
      if (slotframe != NULL)
      {
        *slotframe = slotframe_handle;
      }
      return 1;
    }

    // We don't retrieve ts and ch from the node address
    // if the network reconfiguration has started
    if (current_seq > 0)
    {
      return 0;
    }

    if (slotframe != NULL)
    {
      *slotframe = slotframe_handle;
    }
    if (timeslot != NULL)
    {
      *timeslot = get_node_timeslot(dest);
    }
    /* set per-packet channel offset */
    if (channel_offset != NULL)
    {
      *channel_offset = get_node_channel_offset(dest);
    }
    return 1;
  }
  return 0;
}
/*---------------------------------------------------------------------------*/
static void
new_time_source(const struct tsch_neighbor *old, const struct tsch_neighbor *new)
{
}
/*---------------------------------------------------------------------------*/
#ifdef NETSTACK_CONF_SDN_SLOTFRAME_SIZE_CALLBACK
void orchestra_callback_slotframe_size(uint8_t sf_size, uint16_t seq)
{
  if (seq > current_seq)
  {
    current_seq = seq;
  }
  LOG_INFO("changing slotframe size to %d\n", sf_size);
  if (!tsch_schedule_remove_slotframe(sf_unicast))
  {
    LOG_WARN("Unsuccessful removing dataplane slotframe.\n");
    return;
  }
  /* Create a new slotframe with the given size */
  sf_unicast = tsch_schedule_add_slotframe(slotframe_handle, sf_size);
  // if (!tsch_is_locked())
  // {
  //   struct tsch_neighbor *n = (struct tsch_neighbor *)nbr_table_head(tsch_neighbors);
  //   while (n != NULL)
  //   {
  //     struct tsch_neighbor *next_n = (struct tsch_neighbor *)nbr_table_next(tsch_neighbors, n);
  //     /* get packets in queue */

  //     n = next_n;
  //   }
  // }
}
#endif
/*---------------------------------------------------------------------------*/
static void
init(uint16_t sf_handle)
{
  int i;
  uint16_t rx_timeslot;
  linkaddr_t *local_addr = &linkaddr_node_addr;

  slotframe_handle = sf_handle;
  /* Slotframe for unicast transmissions */
  sf_unicast = tsch_schedule_add_slotframe(slotframe_handle, ORCHESTRA_UNICAST_PERIOD);
  rx_timeslot = get_node_timeslot(local_addr);
  /* Add a Tx link at each available timeslot. Make the link Rx at our own timeslot. */
  for (i = 0; i < ORCHESTRA_UNICAST_PERIOD; i++)
  {
    tsch_schedule_add_link(sf_unicast,
                           LINK_OPTION_SHARED | LINK_OPTION_TX | (i == rx_timeslot ? LINK_OPTION_RX : 0),
                           LINK_TYPE_NORMAL, &tsch_broadcast_address,
                           i, get_node_channel_offset(local_addr), 1);
  }
}
/*---------------------------------------------------------------------------*/
struct orchestra_rule data_plane = {
    init,
    new_time_source,
    select_packet,
    child_added,
    child_removed,
    NULL,
    NULL,
    add_sa_link,
    "data plane",
    ORCHESTRA_UNICAST_PERIOD,
};
