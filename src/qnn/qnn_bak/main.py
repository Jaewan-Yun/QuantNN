import os
import sys
import time

from crypto_data import Crypto
import dataset_list
from encoder_decoder import EncoderDecoder
from feature_extractor import CryptoFeatureExtractorController
from figure_manager import FigureManager
import matplotlib.pyplot as plt
from model_saver import Saver
import numpy as np
import tensorflow as tf
from util import get_num_params


# os.environ['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID'
# os.environ['CUDA_VISIBLE_DEVICES'] = '0, 1'

def fetch_data(input_seq_length, target_seq_length, train_ratio):
    # must set dataset_list, start and end dates before fetching data
    crypto = Crypto(cache_directory='data\\processed_cache')

    # start date of data
    start = {'year': 2016,
             'month': 12,
             'day': 1,
             'hour': 0,
             'minute': 0}
    crypto.set_start_date(start)

    # end date of data
    end = {'year': 2018,
           'month': 4,
           'day': 27,
           'hour': 0,
           'minute': 0}
    crypto.set_end_date(end)

    # select currency pair set
    dataset = dataset_list.AUG2016
    crypto.set_dataset(dataset)

    # select the values to average for target sequence
    exchanges = [dataset_list.GDAX_CHART,
                 dataset_list.POLO_TRADE,
                 dataset_list.KRAK_TRADE]
    products = ['ETH-USD',
                'USDT_ETH',
                'XETHZUSD']
    labels = [(dataset_list.LOW, dataset_list.HIGH,
               dataset_list.OPEN, dataset_list.CLOSE),
              (dataset_list.LOW, dataset_list.HIGH,
               dataset_list.OPEN, dataset_list.CLOSE),
              (dataset_list.LOW, dataset_list.HIGH,
               dataset_list.OPEN, dataset_list.CLOSE)]
    crypto.set_target(exchanges, products, labels)

    # if start and end dates in UNIX are not evenly divisible by 60 seconds,
    # the mutator methods automatically rounds the date down to the nearest t
    print('UTC Start Date  : {}'.format(crypto.start_date))
    print('UTC End Date    : {}'.format(crypto.end_date))
    print('UNIX Start Date : {}'.format(crypto.start_unix))
    print('UNIX End Date   : {}\n'.format(crypto.end_unix))

    # fetch data. this downloads data if cache file is not present
    train_dataset, test_dataset = crypto.get_datasets(
        input_seq_length=input_seq_length,
        target_seq_length=target_seq_length,
        train_ratio=train_ratio,
        load_cache=True,
        use_test_dir=False,
        validate_data=False)

    print('Train Data Inputs Shape : {}'.format(train_dataset.inputs.shape))
    print('Train Data Targets Shape : {}'.format(train_dataset.targets.shape))
    print('Test Data Inputs Shape : {}'.format(test_dataset.inputs.shape))
    print('Test Data Targets Shape : {}\n'.format(test_dataset.targets.shape))

    example = train_dataset.get_example(0)
    print('Example Input Shape : {}'.format(example[0].shape))
    print('Example Target Shape : {}\n'.format(example[1].shape))

    print('Train Num Examples : {}'.format(train_dataset.num_examples))
    print('Test Num Examples : {}'.format(test_dataset.num_examples))
    print('Train Input Depth : {}'.format(train_dataset.input_depth))
    print('Train Target Depth : {}'.format(train_dataset.target_depth))
    print('Test Input Depth : {}'.format(test_dataset.input_depth))
    print('Test Target Depth : {}\n'.format(test_dataset.target_depth))

    return train_dataset, test_dataset


#=========================================================================
# HYPER-PARAMETERS
#=========================================================================

# partition ratio of train to test examples
TRAIN_RATIO = 0.97

# moving window size for each train/test example
INPUT_SEQ_LEN = 35
TARGET_SEQ_LEN = 5

# fetch data
train, test = fetch_data(INPUT_SEQ_LEN, TARGET_SEQ_LEN, TRAIN_RATIO)

# number of training and testing examples calculated from number of
# timestamps in data and the moving window size defined above
NUM_TRAIN = train.num_examples
NUM_TEST = test.num_examples

# number of features at each timestamp (low, high, open, close, ...)
INPUT_DEPTH = train.input_depth
TARGET_DEPTH = train.target_depth

# feature-extractor CNN architecture
KERNEL_SIZES = [5, 5]
KERNEL_FILTERS = [64, 64]
CNN_OUTPUT_SIZE = 512

# encoder-decoder RNN architecture
NUM_UNITS = 512
NUM_LAYERS = 4

# dropout and sampling probabilities
RNN_KEEP_PROB = 0.90
SAMPLING_PROB = 0.00

# training epochs and size of mini-batches
EPOCHS = 1000
BATCH_SIZE = 64
NUM_TRAIN_BATCH = int(np.ceil(NUM_TRAIN / BATCH_SIZE))

# dealing with limited GPU memory. lower this number if getting mem errors
MAX_BATCH_SIZE = 256
NUM_TEST_BATCH = int(np.ceil(NUM_TEST / MAX_BATCH_SIZE))

# optimizer settings
MAX_GRADIENT_NORM = 5.0
LEARNING_RATE_INIT = 0.00001
LEARNING_RATE_DECAY_RATE = 0.9
LEARNING_RATE_DECAY_STEPS = NUM_TRAIN_BATCH

# evaluation involves calculating losses on all test data and saving the
# current learned neural network model. this number is the frequency at
# which evaluation occur, after EVAL_EVERY number of training steps
EVAL_EVERY = 200

# visual update involves calculating only a trivial number of sample train
# and test data to show training progress and predictive performance in
# figures. this number is the frequency at which such calculations occur,
# after SHOW_EVERY number of training steps
SHOW_EVERY = 20


#=========================================================================
# DEFINE INPUT NODES AND BUILD
#=========================================================================

# input sequence placeholder
input_sequence = tf.placeholder(
    dtype=tf.float32,
    shape=(None, INPUT_SEQ_LEN, INPUT_DEPTH),
    name='input_sequence')

# target sequence placeholder
target_sequence = tf.placeholder(
    dtype=tf.float32,
    shape=(None, TARGET_SEQ_LEN, TARGET_DEPTH),
    name='target_sequence')

# RNN dropout keep probability placeholder
rnn_keep_prob = tf.placeholder(
    dtype=tf.float32,
    shape=(),
    name='rnn_keep_prob')


# decoder sampling probability placeholder
sampling_prob = tf.placeholder(
    dtype=tf.float32,
    shape=(),
    name='sampling_prob')

# define CNN feature-extractor
cfe = CryptoFeatureExtractorController(
    input_length=INPUT_SEQ_LEN,
    input_labels=train.input_labels,
    kernel_sizes=KERNEL_SIZES,
    kernel_filters=KERNEL_FILTERS,
    output_size=CNN_OUTPUT_SIZE)

# build CNN
new_sequence, new_length = cfe.build(
    input_ph=input_sequence)

# define RNN encoder-decoder
encoder_decoder = EncoderDecoder(
    num_units=NUM_UNITS,
    num_layers=NUM_LAYERS,
    input_length=new_length,
    input_depth=CNN_OUTPUT_SIZE,
    target_length=TARGET_SEQ_LEN,
    target_depth=TARGET_DEPTH)

# build RNN
outputs = encoder_decoder.build(
    input_ph=new_sequence,
    target_ph=target_sequence,
    keep_prob=rnn_keep_prob,
    sampling_prob=sampling_prob)


#=========================================================================
# TRAINING PARAMS
#=========================================================================

# saves hparam and model variables
model_saver = Saver()

# cost
cost = tf.losses.mean_squared_error(
    labels=target_sequence,
    predictions=outputs) / (BATCH_SIZE * TARGET_SEQ_LEN)

# distance of weights
distance = 0
for trainable in tf.trainable_variables():
    distance += tf.nn.l2_loss(trainable)

# clip gradients
trainable_vars = tf.trainable_variables()
gradients = tf.gradients(cost, trainable_vars)
clipped_gradients, _ = tf.clip_by_global_norm(gradients, MAX_GRADIENT_NORM)

# incremented per train step
global_step = tf.get_variable(
    'global_step',
    shape=(),
    trainable=False,
    initializer=tf.zeros_initializer)

# learning rate decay rate
learning_rate = tf.train.exponential_decay(
    LEARNING_RATE_INIT,
    global_step,
    LEARNING_RATE_DECAY_STEPS,
    LEARNING_RATE_DECAY_RATE,
    staircase=True)

# optimization
optimizer = tf.train.AdamOptimizer(learning_rate, beta1=0.9, beta2=0.999)
train_op = optimizer.apply_gradients(
    grads_and_vars=zip(clipped_gradients, trainable_vars),
    global_step=global_step)

# total number of parameters
n_params = get_num_params()
print('Total number of parameters: {}\n'.format(n_params))


#=========================================================================
# TRAINING
#=========================================================================

def train_model(model_id, model_filename=None):
    """Train the model.
    """
    # default tensorflow session
    sess = tf.Session()

    # initialize variables
    sess.run(tf.global_variables_initializer())

    # restore last session if given
    if model_filename is not None:
        try:
            model_saver.restore_model(sess, model_filename)
            print('Restored model from {}\n'.format(model_filename))
        except Exception as e:
            print('Failed to restore model from {}\n'.format(model_filename), e)
            sys.exit()

    # initialize figures
    fig = FigureManager(
        fig_1_train_sample_rows=7,
        fig_1_rows=30,
        fig_1_cols=16,
        fig_2_rows=6,
        fig_2_cols=2)

    # historical performance
    past_train_cost_list = []
    past_avg_train_cost_list = []
    past_test_cost_list = []
    past_sample_test_cost_list = []
    past_distance_list = []
    past_learning_rate_list = []

    # performance of each training batch
    train_cost_list = []

    # begin training
    for epoch in range(EPOCHS + 1):

        # shuffle training data indices
        shuffle = np.random.permutation(range(NUM_TRAIN))

        # time data preparation pipeline in python
        last_time = 0

        # mini-batch
        for train_batch in range(NUM_TRAIN_BATCH):

            # start and end indices of shuffled data indices for mini-batch
            train_start_index = train_batch * BATCH_SIZE
            train_end_index = train_start_index + BATCH_SIZE - 1
            train_end_index = min(train_end_index, NUM_TRAIN - 1)

            # get mini-batch from shuffled indices
            x, y = train.get_example_set(
                shuffle[train_start_index:train_end_index])

            # run a mini-batch train step
            feed_dict = {input_sequence: x,
                         target_sequence: y,
                         rnn_keep_prob: RNN_KEEP_PROB,
                         sampling_prob: SAMPLING_PROB}
            ops = [train_op, cost]
            # time CPU data prep and GPU computation
            start_time = time.time()
            delta_time_1 = start_time - last_time
            _, train_cost = sess.run(ops, feed_dict=feed_dict)
            end_time = time.time()
            delta_time_2 = end_time - start_time
            last_time = end_time
            print('Data pipeline took {}. GPU compute took {}'.format(
                delta_time_1, delta_time_2))

            # collect train losses
            train_cost_list.append(train_cost)

            # get global step and learning rate
            ops = [global_step, learning_rate]
            current_global_step, current_learning_rate = sess.run(ops)

            # past learning rates of optimizer
            past_learning_rate_list.append(current_learning_rate)

            # console print
            batch_prog = train_end_index * 100 / train.inputs.shape[0]
            description_1 = 'Epoch: {} Batch: {} Epoch Progress: {:3.2f}%'.format(
                epoch, (train_batch + 1), batch_prog)
            description_2 = '\tGlobal Step: {} Learning Rate: {}'.format(
                current_global_step, current_learning_rate)
            description_3 = '\tTraining  Loss: {}'.format(train_cost)
            print(description_1, description_2, description_3, sep='\n')

            # show sample output
            if int(current_global_step) % SHOW_EVERY == 0:

                # compute a sample of training predictions
                step = NUM_TRAIN // fig.get_num_train_figs()
                indices = range(0, NUM_TRAIN, step)
                x, y = train.get_example_set(indices)

                # calculate with no dropout
                feed_dict = {input_sequence: x,
                             target_sequence: y,
                             rnn_keep_prob: 1.0,
                             sampling_prob: 1.0}
                predictions = sess.run(outputs, feed_dict=feed_dict)

                # plot sample training predictions
                fig.plot_predictions(
                    predictions,
                    train.raw_targets,
                    indices,
                    INPUT_SEQ_LEN,
                    TARGET_SEQ_LEN,
                    is_training_data=True)

                # compute a sample of inference predictions
                step = NUM_TEST // fig.get_num_test_figs()
                indices = range(0, NUM_TEST, step)
                x, y = test.get_example_set(indices)

                # calculate with no dropout
                feed_dict = {input_sequence: x,
                             target_sequence: y,
                             rnn_keep_prob: 1.0,
                             sampling_prob: 1.0}
                ops = [outputs, cost]
                [predictions,
                 sample_test_cost] = sess.run(ops, feed_dict=feed_dict)

                # sample inference losses
                past_sample_test_cost_list.append(sample_test_cost)

                # plot sample inference predictions
                fig.plot_predictions(
                    predictions,
                    test.raw_targets,
                    indices,
                    INPUT_SEQ_LEN,
                    TARGET_SEQ_LEN,
                    is_training_data=False)

            # evaluate inference after set amount of training
            if int(current_global_step) % EVAL_EVERY == 0:

                # all past train losses
                past_train_cost_list.extend(train_cost_list)

                # mean of training cost up to evaluation point
                train_cost_avg = np.mean(train_cost_list)
                train_cost_list = []  # reset

                # batch up testing data to fit in GPU memory
                test_cost_list = []
                for test_batch in range(NUM_TEST_BATCH):

                    # start and end indices for current batch
                    test_start_index = test_batch * MAX_BATCH_SIZE
                    test_end_index = test_start_index + MAX_BATCH_SIZE - 1
                    test_end_index = min(test_end_index, NUM_TEST - 1)

                    # get sliding windows
                    x, y = test.get_example_set(
                        range(test_start_index, test_end_index))

                    # run graph on inference data
                    feed_dict = {input_sequence: x,
                                 target_sequence: y,
                                 rnn_keep_prob: 1.0,
                                 sampling_prob: 1.0}
                    test_cost = sess.run(cost, feed_dict=feed_dict)

                    # collect inference performance
                    test_cost_list.append(test_cost)

                # average batched inference loss to get total loss
                test_cost = np.mean(test_cost_list)

                # get l2 distance of variables
                var_distance = sess.run(distance)

                # history of inference performance
                past_avg_train_cost_list.append(train_cost_avg)
                past_test_cost_list.append(test_cost)
                past_distance_list.append(var_distance)

                # console print
                description_4 = '\tInference Loss: {}'.format(test_cost)
                description_5 = '\tL2 Distance of Weights: {}\n'.format(
                    var_distance)
                print(description_4, description_5, sep='\n')

                # create directory and avoid overwriting past models
                dir_str = 'models/model-{}_epoch-{}_batch-{}'
                dir_path = dir_str.format(model_id, epoch, (train_batch + 1))
                while os.path.exists(dir_path):
                    model_id += 1
                    dir_path = dir_str.format(
                        model_id, epoch, (train_batch + 1))
                os.makedirs(dir_path)

                # save model
                model_filename = 'train-loss-{:.3E}_test-loss-{:.3E}'.format(
                    train_cost, test_cost)
                savepath = model_saver.save_model(
                    sess, dir_path, model_filename)
                print('Model saved to {}\n'.format(savepath))

                # plot stats
                fig.plot_stats(
                    train, test,
                    past_train_cost_list,
                    past_avg_train_cost_list,
                    past_test_cost_list,
                    past_sample_test_cost_list,
                    past_learning_rate_list,
                    past_distance_list)

                # save figures
                pdf_filename = 'model_{}_epoch_{}_batch_{}'.format(
                    model_id, epoch, (train_batch + 1))
                fig.save(dir_path, pdf_filename)
                print('Figures saved to {}/{}\n'.format(dir_path, pdf_filename))


#=========================================================================
# MAIN
#=========================================================================

def main():
    """Entry point. Train model.
    """
    MODEL_ID = 1
    train_model(model_id=MODEL_ID)


if __name__ == '__main__':
    main()
