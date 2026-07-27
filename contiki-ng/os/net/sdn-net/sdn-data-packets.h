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
 * \addtogroup sdn-data-packets
 * @{
 *
 * @file sdn-data-packets.h
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief Header for the Contiki/SD-WSN interface
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#ifndef SDN_DATA_PACKETS_H
#define SDN_DATA_PACKETS_H

#include "sys/stimer.h"
#include "net/linkaddr.h"

#ifndef SDN_CONF_DATA_PACKET_INTERVAL
#define SDN_DATA_PACKET_INTERVAL 60 * 1 // 1 pkt/min.
#else
#define SDN_DATA_PACKET_INTERVAL SDN_CONF_DATA_PACKET_INTERVAL
#endif

#ifndef SDN_CONF_MIN_DATA_PACKET_INTERVAL
#define SDN_MIN_DATA_PACKET_INTERVAL (SDN_DATA_PACKET_INTERVAL * 9 / 10)
#else
#define SDN_MIN_DATA_PACKET_INTERVAL SDN_CONF_MIN_DATA_PACKET_INTERVAL
#endif

// typedef struct
// {
//     uint8_t seq,
//     temp,
//     hum;
// } sdn_data_pkt_t;

#if !(SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL)
extern struct etimer data_timer_periodic; /**< Timer for periodic ND */
#endif

/** \brief Initialize ND structures */
void sdn_data_init(void);

#if !(SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL)
/** \brief Reset data sequence number */
void sdn_data_reset_seq(uint16_t new_cycle_seq);
#endif

#if !(SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL)
/** \brief Periodic processing of data structures */
void sdn_data_periodic(void);
#endif

#if SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL
/**
 * \brief Handle an incoming ND message

 */
void sdn_data_input(void);
#endif

#endif

/** @} */