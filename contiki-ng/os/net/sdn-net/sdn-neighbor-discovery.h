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

#ifndef SDN_NEIGHBOR_DISCOVERY_H
#define SDN_NEIGHBOR_DISCOVERY_H

#include "sys/stimer.h"
#include "net/linkaddr.h"

#ifndef SDN_CONF_MAX_ND_INTERVAL
#define SDN_MAX_ND_INTERVAL 60 * 5 // Every 5 mins
#else
#define SDN_MAX_ND_INTERVAL SDN_CONF_MAX_ND_INTERVAL
#endif

#ifndef SDN_CONF_MIN_ND_INTERVAL
#define SDN_MIN_ND_INTERVAL (SDN_MAX_ND_INTERVAL * 4 / 5)
#else
#define SDN_MIN_ND_INTERVAL SDN_CONF_MIN_ND_INTERVAL
#endif

#if BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED || BUILD_WITH_SDN_ORCHESTRA
#ifndef NETSTACK_CONF_SDN_RANK_UPDATED_CALLBACK
#define NETSTACK_CONF_SDN_RANK_UPDATED_CALLBACK orchestra_callback_rank_updated
#endif /* NETSTACK_CONF_ROUTING_NEIGHBOR_ADDED_CALLBACK */
#endif /* BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED */

// #if !(SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL)
typedef struct
{
    /* The ->addr field holds the Rime address of gateway to controller. */
    linkaddr_t addr;
    uint8_t rank;
    int16_t rssi;
} sdn_rank_t;
extern sdn_rank_t my_rank;
// #endif

extern struct etimer nd_timer_periodic; /**< Timer for periodic ND */

/** \brief Initialize ND structures */
void sdn_nd_init(void);

/** \brief Periodic processing of data structures */
void sdn_nd_periodic(void);

/**
 * \brief Handle an incoming ND message

 */
void sdn_nd_input(void);

#endif

/** @} */