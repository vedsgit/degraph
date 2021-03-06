import degraph as dg
from degraph.cairo_plot import StatusPlotter

import tensorflow as tf
import os
import uuid
import traceback
import networkx as nx


RASTER_SHAPE = (200, ) * 2      # Shape of the raster image where the RBF are plotted


def create_summary_writer_factory(output_path: str):
    """
    Create summary writer for Tensorboard.
    :return:
    """
    path = os.path.join(output_path, f"log-{uuid.uuid4()}")
    print(f"log path: {path}")

    def fun():
        return tf.summary.create_file_writer(path)
    return fun


def create_sample_graph():
    """
    Create a sample graph.
    :return: Return an adjacency matrix.
    """
    g = nx.balanced_tree(3, 3)
    # g = nx.grid_2d_graph(5, 5)
    # g = nx.karate_club_graph()
    m = nx.to_numpy_matrix(g)
    return m


@tf.function
def path_length_loss(edges: tf.Tensor):
    """
    Create loss component that penalizes the length of the edges.
    :param edges:
    :return:
    """
    loss_factor = 1.
    edges *= tf.convert_to_tensor(RASTER_SHAPE, dtype=dg.TF_FLOAT)
    lengths = dg.math.path_length(edges)
    # lengths = tf.square(lengths)
    # lengths = tf.abs(lengths - 5.)
    lengths = tf.reduce_mean(lengths) * loss_factor
    return lengths


def test1(output_path: str, log_raster: bool = False):
    graph = dg.GraphRepr(adjacency=create_sample_graph(), dim=len(RASTER_SHAPE))    # Create graph

    plotter = StatusPlotter(graph=graph, path_prefix=os.path.join(output_path, 'step'))
    plotter(index='init')   # Plot init state

    model = dg.Model()
    with model.as_active():
        # Create entity representing edges
        edges = dg.piecewise_linear_edges(graph, steps=25, space_radius=10., name='ed', trainable=True)
        # Create entity representing vertexes
        vx = dg.vertexes(graph, trainable=True, name='vx')

        # Create a raster where Wendland RBF is used to represent the vertexes interaction.
        raster = dg.aggregate_rasters([
            dg.rbf_net_raster(vx, shape=RASTER_SHAPE, rbf='wendland', spread=3.0, peak=1.0)
        ], bias=-1.)

        if log_raster:
            dg.summary_image(raster, scope='raster')
            dg.summary_histogram(raster, scope='raster_histo')

        # Loss contributions
        losses = {
            'metrics.raster_loss': dg.sse_loss(raster),
            'metrics.bounds_loss': dg.unit_sphere_bounds_loss(edges),
            'metrics.path_length_loss': dg.lambda_(path_length_loss, edges)
        }
        for loss_ in losses.items():
            dg.summary_scalar(loss_[1], scope=loss_[0])     # Loss contribution summary (Tensorboard)
        loss = dg.reduce_sum(losses.values(), name='loss')  # Aggregate the individual losses
        dg.summary_scalar(loss, scope='metrics.loss')       # Summarise the overall loss on Tensorboard

    model.summary_writer_factory = create_summary_writer_factory(output_path)
    callbacks = [
        dg.callback.SnapshotCallback(plotter, interval=5),  # Snapshot callback, plot the status every X seconds
    ]

    try:
        # Create optimizer (SGD)
        optimizer = tf.keras.optimizers.SGD(learning_rate=1e-1, decay=2., momentum=0.9, clipnorm=1.0)
        # Run the fitting
        model.fit(1000, loss=loss, optimizer=optimizer, callbacks=callbacks)
    except AssertionError:
        traceback.print_exc()

    plotter(index='end')    # Plot the end state
    print(graph.positions)


# Please set the preferred output path
test1(output_path='/tmp/', log_raster=True)

