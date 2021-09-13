""" Classes for remixing audio files.
(c) 2017 - Dave Rensin - dave@rensin.com

This module contains classes for remixing audio files. It started
as an attempt to re-create the amazing Infinite Jukebox (http://www.infinitejuke.com)
created by Paul Lamere of Echo Nest.

The InfiniteJukebox class can do it's processing in a background thread and
reports progress via the progress_callback arg. To run in a thread, pass do_async=True
to the constructor. In that case, it exposes an Event named play_ready -- which will
be signaled when the processing is complete. The default mode is to run synchronously.

  Async example:

      def MyCallback(percentage_complete_as_float, string_message):
        print "I am now %f percent complete with message: %s" % (percentage_complete_as_float * 100, string_message)

      jukebox = InfiniteJukebox(filename='some_file.mp3', progress_callback=MyCallback, do_async=True)
      jukebox.play_ready.wait()

      <some work here...>

  Non-async example:

      def MyCallback(percentage_complete_as_float, string_message):
        print "I am now %f percent complete with message: %s" % (percentage_complete_as_float * 100, string_message)

      jukebox = InfiniteJukebox(filename='some_file.mp3', progress_callback=MyCallback, do_async=False)

      <blocks until completion... some work here...>

"""

import collections
import librosa
import math
import random
import scipy
import threading

import numpy as np
import sklearn.cluster
import sklearn.metrics

import multiprocessing
import functools
import time

import os
from pathlib import Path
import csv

from utils import CONFIG, CacheOptions

def smap(f):
    return f()

class InfiniteJukebox(object):

    """ Class to "infinitely" remix a song.

    This class will take an audio file (wav, mp3, ogg, etc) and
    (a) decompose it into individual beats, (b) find the tempo
    of the track, and (c) create a play path that you can use
    to play the song approx infinitely.

    The idea is that it will find and cluster beats that are
    musically similar and return them to you so you can automatically
    'remix' the song.

    Attributes:

     play_ready: an Event that triggers when the processing/clustering is complete and
                 playback can begin. This is only defined if you pass do_async=True in the
                 constructor.

    start_index: the start index of the original track before trimming (i.e. leading silence is before this start index)

       duration: the duration (in seconds) of the track after the leading and trailing silences
                 have been removed.

      raw_audio: an array of numpy.Int16 that is suitable for using for playback via pygame
                 or similar modules. If the audio is mono then the shape of the array will
                 be (bytes,). If it's stereo, then the shape will be (2,bytes).

    sample_rate: the sample rate from the audio file. Usually 44100 or 48000

       clusters: the number of clusters used to group the beats. If you pass in a value, then
                 this will be reflected here. If you let the algorithm decide, then auto-generated
                 value will be reflected here.

          beats: a dictionary containing the individual beats of the song in normal order. Each
                 beat will have the following keys:

                         id: the ordinal position of the beat in the song
                      start: the time (in seconds) in the song where this beat occurs
                   duration: the duration (in seconds) of the beat
                     buffer: an array of audio bytes for this beat. it is just raw_audio[start:start+duration]
                    cluster: the cluster that this beat most closely belongs. Beats in the same cluster
                             have similar harmonic (timbre) and chromatic (pitch) characteristics. They
                             will "sound similar"
                    segment: the segment to which this beat belongs. A 'segment' is a contiguous block of
                             beats that belong to the same cluster.
                  amplitude: the loudness of the beat
                       next: the next beat to play after this one, if playing sequentially
            jump_candidates: a list of the other beats in the song to which it is reasonable to jump. Those beats
                             (a) are in the same cluster as the NEXT oridnal beat, (b) are of the same segment position
                             as the next ordinal beat, (c) are in the same place in the measure as the NEXT beat,
                             (d) but AREN'T the next beat.

                 An example of playing the first 32 beats of a song:

                    from Remixatron import InfiniteJukebox
                    from pygame import mixer
                    import time

                    jukebox = InfiniteJukebox('some_file.mp3')

                    pygame.mixer.init(frequency=jukebox.sample_rate)
                    channel = pygame.mixer.Channel(0)

                    for beat in jukebox.beats[0:32]:
                        snd = pygame.Sound(buffer=beat['buffer'])
                        channel.queue(snd)
                        time.sleep(beat['duration'])

    play_vector: a beat play list of 1024^2 items. This represents a pre-computed
                 remix of this song that will last beat['duration'] * 1024 * 1024
                 seconds long. A song that is 120bpm will have a beat duration of .5 sec,
                 so this playlist will last .5 * 1024 * 1024 seconds -- or 145.67 hours.

                 Each item contains:

                    beat: an index into the beats array of the beat to play
                 seq_len: the length of the musical sequence being played
                          in this part of play_vector.
                 seq_pos: this beat's position in seq_len. When
                          seq_len - seq_pos == 0 the song will "jump"

    """

    def __init__(self, filepath, start_beat=1, use_cache = False, clusters=0, max_clusters = 48, progress_callback=None,
                 do_async=False, use_v1=False):

        """ The constructor for the class. Also starts the processing thread.

            Args:

                filepath: the path to the audio file to process
              start_beat: the first beat to play in the file. Should almost always be 1,
                          but you can override it to skip into a specific part of the song.
               use_cache: use cache if it exists
                clusters: the number of similarity clusters to compute. The DEFAULT value
                          of 0 means that the code will try to automatically find an optimal
                          cluster. If you specify your own value, it MUST be non-negative. Lower
                          values will create more promiscuous jumps. Larger values will create higher quality
                          matches, but run the risk of jumps->0 -- which will just loop the
                          audio sequentially ~forever.
            max_clusters: number of clusters to try
       progress_callback: a callback function that will get periodic satatus updates as
                          the audio file is processed. MUST be a function that takes 2 args:

                             percent_complete: FLOAT between 0.0 and 1.0
                                      message: STRING with the progress message
                  use_v1: set to True if you want to use the original auto clustering algorithm.
                          Otherwise, it will use the newer silhouette-based scheme.
        """
        self.__progress_callback = progress_callback
        self.filepath = filepath
        self.__start_beat = start_beat
        self.clusters = clusters
        self.__max_clusters = max_clusters
        self._extra_diag = ""
        self._use_v1 = use_v1
        self.cache_option = CacheOptions.DISCARD

        if use_cache and os.path.isfile(os.path.join(CONFIG['cacheDir'], Path(filepath).stem + '.csv')):
            self.evecs = np.array([])
            self.__load_cache()
        else:
            if do_async == True:
                self.play_ready = threading.Event()
                self.__thread = threading.Thread(target=self.__process_audio)
                self.__thread.start()
            else:
                self.play_ready = None
                self.__process_audio()




    def save_cache(self, cache_evecs = False):
        os.makedirs(CONFIG['cacheDir'], exist_ok=True)
        with open(os.path.join(CONFIG['cacheDir'], Path(self.filepath).stem + '.csv'), 'w', newline='') as csvfile:
            fieldnames = ['start_index', 'cluster']  # , 'stop_index', 'start', 'duration' ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow({'start_index': "",  # jukebox.filename,
                             'cluster': self.avg_amplitude})
            writer.writerow({'start_index': self.__start_beat,
                             'cluster': self.clusters})
            # ,
            # 'stop_index': filepath,
            # 'start': 0,
            # 'duration': jukebox.duration})
            for beat in self.beats:
                writer.writerow({'start_index': beat['start_index'],
                                 'cluster': beat['cluster']})  # ,
                # 'stop_index': beat['stop_index'],
                # 'start': beat['start'],
                # 'duration': beat['duration']})

        if cache_evecs:
            np.save(os.path.join(CONFIG['cacheDir'], Path(self.filepath).stem + '.npy'), self.evecs)

    def remove_cache(self):
        songname = Path(self.filepath).stem
        if self.cache_option == self.cache_option.DISCARD:
            if os.path.isfile(os.path.join(CONFIG['cacheDir'], songname + '.csv')):
                os.remove(os.path.join(CONFIG['cacheDir'], songname + '.csv'))
            if os.path.isfile(os.path.join(CONFIG['cacheDir'], songname + '.npy')):
                os.remove(os.path.join(CONFIG['cacheDir'], songname + '.npy'))
        elif self.cache_option == self.cache_option.KEEP_CACHE:
            if os.path.isfile(os.path.join(CONFIG['cacheDir'], songname + '.npy')):
                os.remove(os.path.join(CONFIG['cacheDir'], songname + '.npy'))

    def __load_cache(self):
        self.beats = []
        with open(os.path.join(CONFIG['cacheDir'], Path(self.filepath).stem + '.csv'), newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for i, beat in enumerate(reader):
                if i == 0:
                    #if beat['start_index'] != self.filepath:
                    #    break
                    self.__report_progress(.8, "loading from cache...")
                    self.avg_amplitude = float(beat['cluster'])

                elif i == 1:
                    start_index_diff = max(0, int(beat['start_index']) - self.__start_beat)
                    self.__start_beat += start_index_diff
                    clusters = int(beat['cluster'])
                elif i >= start_index_diff + 2:
                    self.beats.append({'start_index': int(beat['start_index']),
                                  'cluster': int(beat['cluster'])})#,
                                  #'id': i})  # ,
                    # 'stop_index': beat['stop_index'],
                    # 'start': beat['start'],
                    # 'duration': beat['duration']})

        y, sr = librosa.core.load(self.filepath, mono=False, sr=None)
        y, index = librosa.effects.trim(y)

        self.start_index = index[0]

        self.duration = librosa.core.get_duration(y, sr)
        self.raw_audio = (y * np.iinfo(np.int16).max).astype(np.int16).T.copy(order='C')
        self.sample_rate = sr

        if os.path.isfile(os.path.join(CONFIG['cacheDir'], Path(self.filepath).stem + '.npy')):
            self.evecs = np.load(os.path.join(CONFIG['cacheDir'], Path(self.filepath).stem + '.npy'))

        if self.clusters == 0: # if 0 in config, use what was saved
            self.clusters = clusters
        self.recompute_beat_array(clusters)

        self.time_elapsed = -1

    def recompute_beat_array(self, clusters):

        if (self.clusters != clusters): # if num of clusters different from what was saved

            seg_ids, self.clusters = self.__compute_cluster(self.evecs, clusters, self._use_v1)

            for i, beat in enumerate(self.beats):
                beat['cluster'] = seg_ids[i]
        else:
            self.clusters = clusters

        total_indices = self.raw_audio.shape[0]

        for i, beat in enumerate(self.beats):
            beat['id'] = i
            beat['start'] = (beat['start_index']/total_indices) * self.duration
            beat['quartile'] = beat['id'] // (len(self.beats) / 4.0)

            if i == (len(self.beats) - 1):
                beat['stop_index'] = total_indices
                beat['next'] = self.beats[0]['id']
                beat['duration'] = self.duration - beat['start']
            else:
                beat['stop_index']  = self.beats[i + 1]['start_index']
                beat['next'] = i + 1
                beat['duration'] = ((self.beats[i + 1]['start_index'] - beat['start_index']) / total_indices) * self.duration

            if i == 0:
                beat['segment'] = 0
                beat['is'] = 0
            else:
                if beat['cluster'] != self.beats[i - 1]['cluster']:
                    beat['segment'] = self.beats[i - 1]['segment'] + 1
                    beat['is'] = 0
                else:
                    beat['segment'] = self.beats[i - 1]['segment']
                    beat['is'] = self.beats[i - 1]['is'] + 1

            beat['buffer'] = self.raw_audio[beat['start_index']: beat['stop_index']]

        for beat in self.beats[:-1]:
            jump_candidates = [bx['id'] for bx in self.beats[:beat['id']] if  # only consider beats that are earlier
                               (bx['cluster'] == self.beats[beat['next']]['cluster']) and
                               (bx['is'] == self.beats[beat['next']]['is']) and
                               # (bx['id'] % 4 == beats[beat['next']]['id'] % 4) and # removed as was limiting loop points
                               (bx['segment'] != beat['segment']) and
                               (bx['id'] != beat['next'])]

            if jump_candidates:
                beat['jump_candidates'] = jump_candidates
            else:
                beat['jump_candidates'] = []

        self.beats[-1]['jump_candidates'] = []

    def __process_audio(self):

        """ The main audio processing routine for the thread.

        This routine uses Laplacian Segmentation to find and
        group similar beats in the song.

        This code has been adapted from the sample created by Brian McFee at
        https://librosa.github.io/librosa_gallery/auto_examples/plot_segmentation.html#sphx-glr-auto-examples-plot-segmentation-py
        and is based on his 2014 paper published at http://bmcfee.github.io/papers/ismir2014_spectral.pdf

        I have made some performance improvements, but the basic parts remain (mostly) unchanged
        """

        start = time.time()

        self.__report_progress( .1, "loading file and extracting raw audio")

        #
        # load the file as stereo with a high sample rate and
        # trim the silences from each end
        #

        y, sr = librosa.core.load(self.filepath, mono=False, sr=None)
        y, index = librosa.effects.trim(y)

        self.start_index = index[0]

        self.duration = librosa.core.get_duration(y,sr)
        self.raw_audio = (y * np.iinfo(np.int16).max).astype(np.int16).T.copy(order='C')
        self.sample_rate = sr

        # after the raw audio bytes are saved, convert the samples to mono
        # because the beat detection algorithm in librosa requires it.

        y = librosa.core.to_mono(y)

        self.__report_progress( .2, "computing pitch data and finding beats...")

        # Compute the constant-q chromagram for the samples.

        BINS_PER_OCTAVE = 12 * 3
        N_OCTAVES = 7

        # If multiple cores exist, process cqt and beat track at same time to cut computation time
        if multiprocessing.cpu_count() > 1:
            f_cqt = functools.partial(librosa.cqt, y=y, sr=sr, bins_per_octave=BINS_PER_OCTAVE, n_bins=N_OCTAVES * BINS_PER_OCTAVE)
            f_beat_track = functools.partial(librosa.beat.beat_track, y=y, sr=sr, trim=False)

            with multiprocessing.Pool(processes=2) as pool:
                res = pool.map(smap, [f_cqt, f_beat_track])
                cqt = res[0]
                tempo = res[1][0]
                btz = res[1][1]
        else:
            cqt = librosa.cqt(y=y, sr=sr, bins_per_octave=BINS_PER_OCTAVE, n_bins=N_OCTAVES * BINS_PER_OCTAVE) ######
            tempo, btz = librosa.beat.beat_track(y=y, sr=sr, trim=False)  ##########

        # Cynthia
        # single core: 21s, 23s, 28s, 26s
        # multi core: 19s

        # 08 HOHR
        # single core: 45s, 46s
        # multi core: 37s, 37s

        # Hornet
        # single core: 14s, 12s, 10s
        # multi core: 11s, 11s

        C = librosa.amplitude_to_db( np.abs(cqt), ref=np.max)

        #self.__report_progress( .3, "Finding beats..." )

        ##########################################################
        # To reduce dimensionality, we'll beat-synchronous the CQT
        #tempo, btz = librosa.beat.beat_track(y=y, sr=sr, trim=False) ##########
        # tempo, btz = librosa.beat.beat_track(y=y, sr=sr)
        Csync = librosa.util.sync(C, btz, aggregate=np.median)

        self.tempo = tempo

        # For alignment purposes, we'll need the timing of the beats
        # we fix_frames to include non-beat frames 0 and C.shape[1] (final frame)
        beat_times = librosa.frames_to_time(librosa.util.fix_frames(btz,
                                                                    x_min=0,
                                                                    x_max=C.shape[1]),
                                            sr=sr)

        self.__report_progress( .4, "building recurrence matrix...")
        #####################################################################
        # Let's build a weighted recurrence matrix using beat-synchronous CQT
        # (Equation 1)
        # width=3 prevents links within the same bar
        # mode='affinity' here implements S_rep (after Eq. 8)
        R = librosa.segment.recurrence_matrix(Csync, width=3, mode='affinity',
                                              sym=True)

        # Enhance diagonals with a median filter (Equation 2)
        df = librosa.segment.timelag_filter(scipy.ndimage.median_filter)
        Rf = df(R, size=(1, 7))


        ###################################################################
        # Now let's build the sequence matrix (S_loc) using mfcc-similarity
        #
        #   :math:`R_\text{path}[i, i\pm 1] = \exp(-\|C_i - C_{i\pm 1}\|^2 / \sigma^2)`
        #
        # Here, we take :math:`\sigma` to be the median distance between successive beats.
        #
        mfcc = librosa.feature.mfcc(y=y, sr=sr)
        Msync = librosa.util.sync(mfcc, btz)

        path_distance = np.sum(np.diff(Msync, axis=1)**2, axis=0)
        sigma = np.median(path_distance)
        path_sim = np.exp(-path_distance / sigma)

        R_path = np.diag(path_sim, k=1) + np.diag(path_sim, k=-1)


        ##########################################################
        # And compute the balanced combination (Equations 6, 7, 9)

        deg_path = np.sum(R_path, axis=1)
        deg_rec = np.sum(Rf, axis=1)

        mu = deg_path.dot(deg_path + deg_rec) / np.sum((deg_path + deg_rec)**2)

        A = mu * Rf + (1 - mu) * R_path

        #####################################################
        # Now let's compute the normalized Laplacian (Eq. 10)
        L = scipy.sparse.csgraph.laplacian(A, normed=True)


        # and its spectral decomposition
        _, evecs = scipy.linalg.eigh(L)


        # We can clean this up further with a median filter.
        # This can help smooth over small discontinuities
        evecs = scipy.ndimage.median_filter(evecs, size=(9, 1))

        self.evecs = evecs #save intermediate step for caching

        # Cluster beats
        seg_ids, self.clusters = self.__compute_cluster(self.evecs, self.clusters, self._use_v1)

        # Get the amplitudes and beat-align them
        self.__report_progress( .6, "getting amplitudes")

        # newer versions of librosa have renamed the rmse function

        if hasattr(librosa.feature,'rms'):
            amplitudes = librosa.feature.rms(y=y)
        else:
            amplitudes = librosa.feature.rmse(y=y)

        ampSync = librosa.util.sync(amplitudes, btz)

        # create a list of tuples that include the ordinal position, the start time of the beat,
        # the cluster to which the beat belongs and the mean amplitude of the beat

        zbeat_tuples = zip(range(0,len(btz)), beat_times, seg_ids, ampSync[0].tolist())
        beat_tuples =tuple(zbeat_tuples)

        info = []

        bytes_per_second = int(round(len(self.raw_audio) / self.duration))

        last_cluster = -1
        current_segment = -1
        segment_beat = 0

        for i in range(0, len(beat_tuples)):
            final_beat = {}
            final_beat['start'] = float(beat_tuples[i][1])
            final_beat['cluster'] = int(beat_tuples[i][2])
            final_beat['amplitude'] = float(beat_tuples[i][3])

            if final_beat['cluster'] != last_cluster:
                current_segment += 1
                segment_beat = 0
            else:
                segment_beat += 1

            final_beat['segment'] = current_segment
            final_beat['is'] = segment_beat

            last_cluster = final_beat['cluster']

            if i == len(beat_tuples) - 1:
                final_beat['duration'] = self.duration - final_beat['start']
            else:
                final_beat['duration'] = beat_tuples[i+1][1] - beat_tuples[i][1]

            if ( (final_beat['start'] * bytes_per_second) % 2 > 1.5 ):
                final_beat['start_index'] = int(math.ceil(final_beat['start'] * bytes_per_second))
            else:
                final_beat['start_index'] = int(final_beat['start'] * bytes_per_second)

            final_beat['stop_index'] = int(math.ceil((final_beat['start'] + final_beat['duration']) * bytes_per_second))

            # save pointers to the raw bytes for each beat with each beat.
            final_beat['buffer'] = self.raw_audio[ final_beat['start_index'] : final_beat['stop_index'] ]

            info.append(final_beat)

        #self.__report_progress( .7, "truncating to fade point...")

        # get the max amplitude of the beats
        # max_amplitude = max([float(b['amplitude']) for b in info])
        avg_amplitude = sum([float(b['amplitude']) for b in info]) / len(info)

        # assume that the fade point of the song is the last beat of the song that is >= 75% of
        # the max amplitude.

        self.avg_amplitude = avg_amplitude

        fade = len(info) - 1

        #for b in reversed(info):
        #    if b['amplitude'] >= (.75 * avg_amplitude):
        #        fade = info.index(b)
        #        break

        # truncate the beats to [start:fade + 1]
        beats = info[self.__start_beat:fade + 1]

        loop_bounds_begin = self.__start_beat

        self.__report_progress( .8, "computing final beat array and finding loops...")

        # assign final beat ids
        for beat in beats:
            beat['id'] = beats.index(beat)
            beat['quartile'] = beat['id'] // (len(beats) / 4.0)

        # compute a coherent 'next' beat to play. This is always just the next ordinal beat
        # unless we're at the end of the song. Then it gets a little trickier.

        for beat in beats[:-1]:
            #if beat == beats[-1]:

                # if we're at the last beat, then we want to find a reasonable 'next' beat to play. It should (a) share the
                # same cluster, (b) be in a logical place in its measure, (c) be after the computed loop_bounds_begin, and
                # is in the first half of the song. If we can't find such an animal, then just return the beat
                # at loop_bounds_begin

                # beat['next'] = next( (b['id'] for b in beats if b['cluster'] == beat['cluster'] and
                #                       b['id'] % 4 == (beat['id'] + 1) % 4 and
                #                       b['id'] <= (.5 * len(beats)) and
                #                       b['id'] >= loop_bounds_begin), loop_bounds_begin )
                #beat['next'] = beats[0]['id']
            #else:
            beat['next'] = beat['id'] + 1

            # find all the beats that (a) are in the same cluster as the NEXT oridnal beat, (b) are of the same
            # cluster position as the next ordinal beat, (c) are in the same place in the measure as the NEXT beat,
            # (d) but AREN'T the next beat, and (e) AREN'T in the same cluster as the current beat.
            #
            # THAT collection of beats contains our jump candidates

            jump_candidates = [bx['id'] for bx in beats[:beat['id']] if # only consider beats that are earlier
                               (bx['cluster'] == beats[beat['next']]['cluster']) and
                               (bx['is'] == beats[beat['next']]['is']) and
                               #(bx['id'] % 4 == beats[beat['next']]['id'] % 4) and # removed as was limiting loop points
                               (bx['segment'] != beat['segment']) and
                               (bx['id'] != beat['next'])]

            if jump_candidates:
                beat['jump_candidates'] = jump_candidates
            else:
                beat['jump_candidates'] = []

        beats[-1]['jump_candidates'] = []
        beats[-1]['next'] = beats[0]['id']

        # save off the segment count

        self.segments = max([b['segment'] for b in beats]) + 1

        # we don't want to ever play past the point where it's impossible to loop,
        # so let's find the latest point in the song where there are still jump
        # candidates and make sure that we can't play past it.

        # last_chance = len(beats) - 1
        #
        # for b in reversed(beats):
        #     if len(b['jump_candidates']) > 0:
        #         last_chance = beats.index(b)
        #         break

        # if we play our way to the last beat that has jump candidates, then just skip
        # to the earliest jump candidate rather than enter a section from which no
        # jumping is possible.

        #beats[last_chance]['next'] = min(beats[last_chance]['jump_candidates'])

        # store the beats that start after the last jumpable point. That's
        # the outro to the song. We can use these
        # beasts to create a sane ending for a fixed-length remix

        # outro_start = last_chance + 1 + self.__start_beat
        #
        # if outro_start >= len(info):
        #     self.outro = []
        # else:
        #     self.outro = info[outro_start:]

        #
        # Computing play_vector is removed in this as it loops live
        #

        random.seed()

        play_vector = []

        # save off the beats array and play_vector. Signal
        # the play_ready event (if it's been set)

        self.beats = beats
        self.play_vector = play_vector

        self.__report_progress(1.0, "finished processing")

        if self.play_ready:
            self.play_ready.set()

        self.time_elapsed = time.time() - start

    def __report_progress(self, pct_done, message):

        """ If a reporting callback was passed, call it in order
            to mark progress.
        """
        if self.__progress_callback:
            self.__progress_callback(pct_done, message, self.filepath)

    def __compute_cluster(self, evecs, clusters, use_v1 = False):

        # cumulative normalization is needed for symmetric normalize laplacian eigenvectors
        Cnorm = np.cumsum(evecs ** 2, axis=1) ** 0.5

        # If we want k clusters, use the first k normalized eigenvectors.
        # Fun exercise: see how the segmentation changes as you vary k

        self.__report_progress(.5, "clustering...")

        # if a value for clusters wasn't passed in, then we need to auto-cluster
        if clusters <= 0:

            # if we've been asked to use the original auto clustering algorithm, otherwise
            # use the new and improved one that accounts for silhouette scores.

            if use_v1:
                clusters, seg_ids = self.__compute_best_cluster(evecs, Cnorm)
            else:
                clusters, seg_ids = self.__compute_best_cluster_with_sil(evecs, Cnorm)
        else:
            # otherwise, just use the cluster value passed in

            self.__report_progress(.51, "using %d clusters" % clusters)

            X = evecs[:, :clusters] / Cnorm[:, clusters - 1:clusters]

            while (np.any(np.isnan(X))) and (not np.all(np.isfinite(X))): # if input is invalid, increment until a valid input is calculated
                clusters += 1
                X = evecs[:, :clusters] / Cnorm[:, clusters - 1:clusters]

            seg_ids = sklearn.cluster.KMeans(n_clusters=clusters, max_iter=1000,
                                             random_state=0, n_init=1000, n_jobs=-1).fit_predict(X)

        return seg_ids, clusters

    def __compute_best_cluster_with_sil(self, evecs, Cnorm):

        ''' Attempts to compute optimum clustering

            Uses the the silhouette score to pick the best number of clusters.
            See: https://en.wikipedia.org/wiki/Silhouette_(clustering)

            PARAMETERS:
                evecs: Eigen-vectors computed from the segmentation algorithm
                Cnorm: Cumulative normalization of evecs. Easier to pass it in than
                       compute it from scratch here.

            KEY DEFINITIONS:

                  Clusters: buckets of musical similarity
                  Segments: contiguous blocks of beats belonging to the same cluster
                Silhouette: A score given to a cluster that measures how well the cluster
                            members fit together. The value is from -1 to +1. Higher values
                            indicate higher quality.
                   Orphans: Segments with only one beat. The presence of orphans is a potential
                            sign of overfitting.

            SUMMARY:

                There are lots of things that might indicate one cluster count is better than another.
                High silhouette scores for the candidate clusters mean that the jumps will be higher
                quality.

                On the other hand, we could easily choose so many clusters that everyone has a great
                silhouette score but none of the beats have other segments into which they can jump.
                That will be a pretty boring result!

                So, the cluster/segment ratio matters, too The higher the number, the more places (on average)
                a beat can jump. However, if the beats aren't very similar (low silhouette scores) then
                the jumps won't make any musical sense.

                So, we can't just choose the cluster count with the highest average silhouette score or the
                highest cluster/segment ratio.

                Instead, we comput a simple fitness score of:
                        cluster_count * ratio * average_silhouette

                Finally, segments with only one beat are a potential (but not definite) sign of overfitting.
                We call these one-beat segments 'orphans'. We want to keep an eye out for those and slightly
                penalize any candidate cluster count that contains orphans.

                If we find an orphan, we scale the fitness score by .8 (ie. penalize it 20%). That's
                enough to push any candidate cluster count down the stack rank if orphans aren't
                otherwise very common across most of the other cluster count choices.

        '''

        self._clusters_list = []

        best_cluster_size = 0
        best_labels = None
        best_cluster_score = 0

        # we need at least 3 clusters for any song and shouldn't need to calculate more than
        # 48 clusters for even a really complicated peice of music.

        for n_clusters in range(self.__max_clusters, 2, -1):

            self.__report_progress(.51, "Testing a cluster value of %d..." % n_clusters)

            # compute a matrix of the Eigen-vectors / their normalized values
            X = evecs[:, :n_clusters] / Cnorm[:, n_clusters-1:n_clusters]

            if (not np.any(np.isnan(X))) and (np.all(np.isfinite(X))): # ensure input is valid

                # create the candidate clusters and fit them
                clusterer = sklearn.cluster.KMeans(n_clusters=n_clusters, max_iter=300,
                                                   random_state=0, n_init=20, n_jobs=-1) # multiprocess

                cluster_labels = clusterer.fit_predict(X)

                # get some key statistics, including how well each beat in the cluster resemble
                # each other (the silhouette average), the ratio of segments to clusters, and the
                # length of the smallest segment in this cluster configuration

                silhouette_avg = sklearn.metrics.silhouette_score(X, cluster_labels)

                ratio, min_segment_len = self.__segment_stats_from_labels(cluster_labels.tolist())

                # We need to grade each cluster according to how likely it is to produce a good
                # result. There are a few factors to look at.
                #
                # First, we can look at how similar the beats in each cluster (on average) are for
                # this candidate cluster size. This is known as the silhouette score. It ranges
                # from -1 (very bad) to 1 (very good).
                #
                # Another thing we can look at is the ratio of clusters to segments. Higher ratios
                # are preferred because they afford each beat in a cluster the opportunity to jump
                # around to meaningful places in the song.
                #
                # All other things being equal, we prefer a higher cluster count to a lower one
                # because it will tend to make the jumps more selective -- and therefore higher
                # quality.
                #
                # Lastly, if we see that we have segments equal to just one beat, that might be
                # a sign of overfitting. We call these one beat segments 'orphans'. Some songs,
                # however, will have orphans no matter what cluster count you use. So, we don't
                # want to throw out a cluster count just because it has orphans. Instead, we
                # just de-rate its fitness score. If most of the cluster candidates have orphans
                # then this won't matter in the overall scheme because everyone will be de-rated
                # by the same scaler.
                #
                # Putting this all together, we muliply the cluster count * the average
                # silhouette score for the clusters in this candidate * the ratio of clusters to
                # segments. Then we scale (or de-rate) the fitness score by whether or not is has
                # orphans in it.

                orphan_scaler = .8 if min_segment_len == 1 else 1

                cluster_score = n_clusters * silhouette_avg * ratio * orphan_scaler
                #cluster_score = ((n_clusters/48.0) * silhouette_avg * (ratio/10.0)) * orphan_scaler

                # if this cluster count has a score that's better than the best score so far, store
                # it for later.

                if cluster_score >= best_cluster_score:
                    best_cluster_score = cluster_score
                    best_cluster_size = n_clusters
                    best_labels = cluster_labels

        # return the best results
        return (best_cluster_size, best_labels)

    @staticmethod
    def __segment_count_from_labels(labels):

        ''' Computes the number of unique segments from a set of ordered labels. Segements are
            contiguous beats that belong to the same cluster. '''

        segment_count = 0
        previous_label = -1

        for label in labels:
            if label != previous_label:
                previous_label = label
                segment_count += 1

        return segment_count

    def __segment_stats_from_labels(self, labels):
        ''' Computes the segment/cluster ratio and min segment size value given an array
            of labels. '''

        segment_count = 0.0
        segment_length = 0
        clusters = max(labels) + 1

        previous_label = -1

        segment_lengths = []

        for label in labels:
            if label != previous_label:
                previous_label = label
                segment_count += 1.0

                if segment_length > 0:
                    segment_lengths.append(segment_length)

                segment_length = 1
            else:
                segment_length +=1

        # self.__report_progress( .52, "clusters: %d,  ratio: %f,  min_seg: %d" % (clusters, segment_count/len(labels), segment_length) )

        return float(segment_count) / float(clusters), min(segment_lengths)

    def __compute_best_cluster(self, evecs, Cnorm):

        ''' Attempts to compute optimum clustering from a set of simplified
            hueristics. This method has been deprecated in favor of code above that takes into
            account the average silhouette score of each cluster. You can force the code to use
            this method by passing in use_v1=True in the constructor.

            PARAMETERS:
                evecs: Eigen-vectors computed from the segmentation algorithm
                Cnorm: Cumulative normalization of evecs. Easier to pass it in than
                       compute it from scratch here.

            KEY DEFINITIONS:

                Clusters: buckets of musical similarity
                Segments: contiguous blocks of beats belonging to the same cluster
                 Orphans: clusters that only belong to one segment
                    Stub: a cluster with less than N beats. Stubs are a sign of
                          overfitting

            SUMMARY:

                Group the beats in [8..64] clusters. They key metric is the segment:cluster ratio.
                This value gives the avg number of different segments to which a cluster
                might belong. The higher the value, the more diverse the playback because
                the track can jump more freely. There is a balance, however, between this
                ratio and the number of clusters. In general, we want to find the highest
                numeric cluster that has a ratio of segments:clusters nearest 4.
                That ratio produces the most musically pleasing results.

                Basically, we're looking for the highest possible cluster # that doesn't
                obviously overfit.

                Someday I'll implement a proper RMSE algorithm...
        '''

        self._clusters_list = []

        # We compute the clusters between 4 and 64. Owing to the inherent
        # symmetry of Western popular music (including Jazz and Classical), the most
        # pleasing musical results will often, though not always, come from even cluster values.

        for ki in range(4,64, 2):

            # compute a matrix of the Eigen-vectors / their normalized values
            X = evecs[:, :ki] / Cnorm[:, ki-1:ki]

            if (not np.any(np.isnan(X))) and (np.all(np.isfinite(X))): # ensure input is valid
                # cluster with candidate ki
                labels = sklearn.cluster.KMeans(n_clusters=ki, max_iter=1000,
                                                random_state=0, n_init=20, n_jobs=-1).fit_predict(X)

                entry = {'clusters':ki, 'labels':labels}

                # create an array of dictionary entries containing (a) the cluster label,
                # (b) the number of total beats that belong to that cluster, and
                # (c) the number of segments in which that cluster appears.

                lst = []

                for i in range(0,ki):
                    lst.append( {'label':i, 'beats':0, 'segs':0} )

                last_label = -1

                for l in labels:

                    if l != last_label:
                        lst[l]['segs'] += 1
                        last_label = l

                    lst[l]['beats'] += 1

                entry['cluster_map'] = lst

                # get the average number of segments to which a cluster belongs
                entry['seg_ratio'] = np.mean([l['segs'] for l in entry['cluster_map']])

                self._clusters_list.append(entry)

        # get the max cluster with the segments/cluster ratio nearest to 4. That
        # will produce the most musically pleasing effect

        max_seg_ratio = max( [cl['seg_ratio'] for cl in self._clusters_list] )
        max_seg_ratio = min( max_seg_ratio, 4 )

        final_cluster_size = max(cl['clusters'] for cl in self._clusters_list if cl['seg_ratio'] >= max_seg_ratio)

        # compute a very high fidelity set of clusters using our selected cluster size.
        X = evecs[:, :final_cluster_size] / Cnorm[:, final_cluster_size-1:final_cluster_size]
        labels = sklearn.cluster.KMeans(n_clusters=final_cluster_size, max_iter=1000,
                                        random_state=0, n_init=1000, n_jobs=-1).fit_predict(X)

        # labels = next(c['labels'] for c in self._clusters_list if c['clusters'] == final_cluster_size)

        # return a tuple of (winning cluster size, [array of cluster labels for the beats])
        return (final_cluster_size, labels)

    def __add_log(self, line):
        """Convenience method to add debug logging info for later"""

        self._extra_diag += line + "\n"
