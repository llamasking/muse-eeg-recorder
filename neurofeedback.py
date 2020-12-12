#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Estimate Relaxation from Band Powers

This example shows how to buffer, epoch, and transform EEG data from a single
electrode into values for each of the classic frequencies (e.g. alpha, beta, theta)
Furthermore, it shows how ratios of the band powers can be used to estimate
mental state for neurofeedback.

The neurofeedback protocols described here are inspired by
*Neurofeedback: A Comprehensive Review on System Design, Methodology and Clinical Applications* by Marzbani et. al

Adapted from https://github.com/NeuroTechX/bci-workshop
"""

import numpy as np  # Module that simplifies computations on matrices
import matplotlib.pyplot as plt  # Module used for plotting
from pylsl import StreamInlet, resolve_byprop  # Module to receive EEG data
import utils  # Our own utility functions
import csv  # We need to write to CSV files
from datetime import datetime  # We need time since everything is rather time sensitive.

# Handy little enum to make code more readable


class Band:
    Delta = 0
    Theta = 1
    Alpha = 2
    Beta = 3


""" EXPERIMENTAL PARAMETERS """
# Modify these to change aspects of the signal processing

# Length of the EEG data buffer (in seconds)
# This buffer will hold last n seconds of data and be used for calculations
BUFFER_LENGTH = 5

# Length of the epochs used to compute the FFT (in seconds)
EPOCH_LENGTH = 1

# Amount of overlap between two consecutive epochs (in seconds)
OVERLAP_LENGTH = 0.8

# Amount to 'shift' the start of each next consecutive epoch
SHIFT_LENGTH = EPOCH_LENGTH - OVERLAP_LENGTH

# Index of the channel(s) (electrodes) to be used
# 0 = left ear, 1 = left forehead, 2 = right forehead, 3 = right ear
INDEX_CHANNEL = [2]

if __name__ == "__main__":
    """ 0. SETUP FILES TO RECORD TO """
    ## Adds a label to the first row of each column
    # Write raw EEG data to data.csv
    with open('eeg_data.csv', 'w') as eegFile:
        csv.writer(eegFile).writerow(["Time", "Alpha", "Beta", "Delta", "Theta"])

    # Write parsed metrics to metrics.csv
    with open('eeg_metrics.csv', 'w') as eegFile:
        csv.writer(eegFile).writerow(["Time", "Alpha Relaxation", "Beta Concentration", "Theta Relaxation"])


    """ 1. CONNECT TO EEG STREAM """

    # Search for active LSL streams
    print('Looking for an EEG stream...')
    streams = resolve_byprop('type', 'EEG', timeout=2)
    if len(streams) == 0:
        raise RuntimeError('Can\'t find EEG stream.')

    # Set active EEG stream to inlet and apply time correction
    print("Start acquiring data")
    inlet = StreamInlet(streams[0], max_chunklen=12)
    eeg_time_correction = inlet.time_correction()

    # Get the stream info and description
    info = inlet.info()
    description = info.desc()

    # Get the sampling frequency
    # This is an important value that represents how many EEG data points are
    # collected in a second. This influences our frequency band calculation.
    # for the Muse 2016, this should always be 256
    fs = int(info.nominal_srate())

    """ 2. INITIALIZE BUFFERS """

    # Initialize raw EEG data buffer
    eeg_buffer = np.zeros((int(fs * BUFFER_LENGTH), 1))
    filter_state = None  # for use with the notch filter

    # Compute the number of epochs in "buffer_length"
    n_win_test = int(np.floor((BUFFER_LENGTH - EPOCH_LENGTH) /
                              SHIFT_LENGTH + 1))

    # Initialize the band power buffer (for plotting)
    # bands will be ordered: [delta, theta, alpha, beta]
    band_buffer = np.zeros((n_win_test, 4))

    """ 3. GET DATA """

    # The try/except structure allows to quit the while loop by aborting the
    # script with <Ctrl-C>
    print('Press Ctrl-C in the console to break the while loop.')

    try:
        # Get time at recording start
        startTime = datetime.now()

        # Open files
        rawFile =  open('eeg_data.csv', 'a')
        metricsFile = open('eeg_metrics.csv', 'a')

        # The following loop acquires data, computes band powers, and calculates neurofeedback metrics based on those band powers
        while True:

            # Get the time since the start of the script.
            timeSinceStart = (datetime.now() -
                              startTime).total_seconds()

            """ 3.1 ACQUIRE DATA """
            # Obtain EEG data from the LSL stream
            eeg_data, timestamp = inlet.pull_chunk(
                timeout=1, max_samples=int(SHIFT_LENGTH * fs))

            # Only keep the channel we're interested in
            ch_data = np.array(eeg_data)[:, INDEX_CHANNEL]

            # Update EEG buffer with the new data
            eeg_buffer, filter_state = utils.update_buffer(
                eeg_buffer, ch_data, notch=True,
                filter_state=filter_state)

            """ 3.2 COMPUTE BAND POWERS """
            # Get newest samples from the buffer
            data_epoch = utils.get_last_data(eeg_buffer,
                                             EPOCH_LENGTH * fs)

            # Compute band powers
            band_powers = utils.compute_band_powers(data_epoch, fs)
            band_buffer, _ = utils.update_buffer(band_buffer,
                                                 np.asarray([band_powers]))
            # Compute the average band powers for all epochs in buffer
            # This helps to smooth out noise
            smooth_band_powers = np.mean(band_buffer, axis=0)

            print('Delta: ', band_powers[Band.Delta], ' Theta: ', band_powers[Band.Theta],
                  ' Alpha: ', band_powers[Band.Alpha], ' Beta: ', band_powers[Band.Beta])

            """ 3.3 COMPUTE NEUROFEEDBACK METRICS """
            # These metrics could also be used to drive brain-computer interfaces

            # Alpha Protocol:
            # Simple redout of alpha power, divided by delta waves in order to rule out noise
            alpha_metric = smooth_band_powers[Band.Alpha] / \
                smooth_band_powers[Band.Delta]
            print('Alpha Relaxation: ', alpha_metric)

            # Beta Protocol:
            # Beta waves have been used as a measure of mental activity and concentration
            # This beta over theta ratio is commonly used as neurofeedback for ADHD
            beta_metric = smooth_band_powers[Band.Beta] / \
                smooth_band_powers[Band.Theta]
            print('Beta Concentration: ', beta_metric)

            # Alpha/Theta Protocol:
            # This is another popular neurofeedback metric for stress reduction
            # Higher theta over alpha is supposedly associated with reduced anxiety
            theta_metric = smooth_band_powers[Band.Theta] / \
                smooth_band_powers[Band.Alpha]
            print('Theta Relaxation: ', theta_metric)

            """ 3.4 WRITE RAW DATA AND METRICS """
            # Write raw EEG data to data.csv
            eegData = [timeSinceStart,
                       smooth_band_powers[Band.Alpha],
                       smooth_band_powers[Band.Beta],
                       smooth_band_powers[Band.Delta],
                       smooth_band_powers[Band.Theta]]
            csv.writer(rawFile).writerow(eegData)

            # Write parsed metrics to metrics.csv
            eegMetrics = [timeSinceStart, alpha_metric, beta_metric, theta_metric]
            csv.writer(metricsFile).writerow(eegMetrics)


    except KeyboardInterrupt:
        print('Closing!')
