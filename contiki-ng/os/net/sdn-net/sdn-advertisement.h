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
 * \addtogroup sdn-advertisement
 * @{
 *
 * @file sdn-advertisement.h
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief Header for the Contiki/SD-WSN interface
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#ifndef SDN_ADVERTISEMENT_H
#define SDN_ADVERTISEMENT_H

#include "sys/stimer.h"
#include "net/linkaddr.h"

#ifndef SDN_CONF_MAX_NA_INTERVAL
#define SDN_MAX_NA_INTERVAL 60 * 5
#else
#define SDN_MAX_NA_INTERVAL SDN_CONF_MAX_NA_INTERVAL
#endif

#ifndef SDN_CONF_MIN_NA_INTERVAL
#define SDN_MIN_NA_INTERVAL (SDN_MAX_NA_INTERVAL * 4 / 5)
#else
#define SDN_MIN_NA_INTERVAL SDN_CONF_MIN_NA_INTERVAL
#endif

extern struct etimer na_timer_periodic; /**< Timer for periodic NA */

#if !BUILD_WITH_SDN_CONTROLLER_SERIAL
/** \brief Reset NA sequence number */
void sdn_na_reset_seq(uint16_t new_cycle_seq);
#endif

/** \brief Initialize ND structures */
void sdn_na_init(void);

/** \brief Periodic processing of data structures */
void sdn_na_periodic(void);

/**
 * \brief Handle an incoming ND message

 */
#if SDN_CONTROLLER || BUILD_WITH_SDN_CONTROLLER_SERIAL
void sdn_na_input(void);
#endif

#endif

/** @} */