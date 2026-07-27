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
 * \addtogroup sdn-power-measurement
 * @{
 *
 * @file sdn-routing.c
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief Sensor nodes power measurement header
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#ifndef SDN_POWER_MEASUREMENT_H
#define SDN_POWER_MEASUREMENT_H

extern uint64_t moving_avg_power;

/** \brief The period at which Energest statistics will be logged */
#ifdef SDN_POWER_MEASUREMENT_CONF_PERIOD
#define SDN_POWER_MEASUREMENT_PERIOD SDN_POWER_MEASUREMENT_CONF_PERIOD
#else /* SIMPLE_ENERGEST_CONF_PERIOD */
#define SDN_POWER_MEASUREMENT_PERIOD (CLOCK_SECOND * 10)
#endif /* SIMPLE_ENERGEST_CONF_PERIOD */

#ifdef SDN_POWER_MEASUREMENT_CONF_INIT_POWER
#define SDN_POWER_MEASUREMENT_INIT_POWER SDN_POWER_MEASUREMENT_CONF_INIT_POWER
#else /* ROUTE_CONF_ENTRIES */
#define SDN_POWER_MEASUREMENT_INIT_POWER 1000
#endif /* ROUTE_CONF_ENTRIES */

#ifdef SDN_POWER_MEASUREMENT_CONF_VOLTAGE
#define SDN_POWER_MEASUREMENT_VOLTAGE SDN_POWER_MEASUREMENT_CONF_VOLTAGE
#else /* ROUTE_CONF_ENTRIES */
#define SDN_POWER_MEASUREMENT_VOLTAGE 3
#endif /* ROUTE_CONF_ENTRIES */

// for charge calculations
// CC2650_MHZ = 48
// CC2650_RADIO_TX_CURRENT_MA          = 9.100 # at 5 dBm, from CC2650 datasheet
// CC2650_RADIO_RX_CURRENT_MA          = 5.900 # from CC2650 datasheet
// CC2650_RADIO_CPU_ON_CURRENT         = 0.061 * CC2650_MHZ # from CC2650 datasheet
// CC2650_RADIO_CPU_SLEEP_CURRENT      = 1.335 # empirical
// CC2650_RADIO_CPU_DEEP_SLEEP_CURRENT = 0.010 # empirical

#ifdef SDN_POWER_MEASUREMENT_CONF_TX
#define SDN_POWER_MEASUREMENT_TX SDN_POWER_MEASUREMENT_CONF_TX
#else /* ROUTE_CONF_ENTRIES */
#define SDN_POWER_MEASUREMENT_TX 9.1
#endif /* ROUTE_CONF_ENTRIES */

#ifdef SDN_POWER_MEASUREMENT_CONF_RX
#define SDN_POWER_MEASUREMENT_RX SDN_POWER_MEASUREMENT_CONF_RX
#else /* ROUTE_CONF_ENTRIES */
#define SDN_POWER_MEASUREMENT_RX 5.9
#endif /* ROUTE_CONF_ENTRIES */

#ifdef SDN_POWER_MEASUREMENT_CONF_CPU
#define SDN_POWER_MEASUREMENT_CPU SDN_POWER_MEASUREMENT_CONF_CPU
#else /* ROUTE_CONF_ENTRIES */
#define SDN_POWER_MEASUREMENT_CPU 0.061
#endif /* ROUTE_CONF_ENTRIES */

#ifdef SDN_POWER_MEASUREMENT_CONF_LPM
#define SDN_POWER_MEASUREMENT_LPM SDN_POWER_MEASUREMENT_CONF_LPM
#else /* ROUTE_CONF_ENTRIES */
#define SDN_POWER_MEASUREMENT_LPM 1.335
#endif /* ROUTE_CONF_ENTRIES */

#ifdef SDN_POWER_MEASUREMENT_CONF_DLPM
#define SDN_POWER_MEASUREMENT_DLPM SDN_POWER_MEASUREMENT_CONF_DPM
#else /* ROUTE_CONF_ENTRIES */
#define SDN_POWER_MEASUREMENT_DLPM 0.01
#endif /* ROUTE_CONF_ENTRIES */

/**
 * Initialize the deployment module
 */
void sdn_power_measurement_init(void);

#endif /* SDN_POWER_MEASUREMENT_H */

/** @} */