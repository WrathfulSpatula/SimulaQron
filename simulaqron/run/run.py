import logging
from time import sleep
from importlib import reload
# from multiprocessing.pool import Pool
from concurrent.futures import ProcessPoolExecutor as Pool
# from pathos.multiprocessing import ProcessPool as Pool
# from pathos.multiprocessing import _ProcessPool as Pool

# import netsquid as ns

from netqasm.sdk.shared_memory import reset_memories
from netqasm.logging import get_netqasm_logger
from netqasm.yaml_util import dump_yaml
from netqasm.output import save_all_struct_loggers, reset_struct_loggers
from netqasm.sdk.classical_communication import reset_socket_hub
# from squidasm.backend.backend import Backend
# from squidasm.network import reset_network
# from squidasm.queues import reset_queues

from simulaqron.network import Network
from simulaqron.settings import simulaqron_settings, SimBackend
from simulaqron.toolbox import has_module

logger = get_netqasm_logger()


def as_completed(futures, names=None, sleep_time=0):
    futures = list(futures)
    if names is not None:
        names = list(names)
    while len(futures) > 0:
        for i, future in enumerate(futures):
            # if future.ready():
            if future.done():
                futures.pop(i)
                if names is None:
                    yield future
                else:
                    name = names.pop(i)
                    yield future, name
        if sleep_time > 0:
            sleep(sleep_time)


def reset(save_loggers=False):
    if save_loggers:
        save_all_struct_loggers()
    # ns.sim_reset()
    reset_memories()
    # reset_network()
    # reset_queues()
    reset_socket_hub()
    reset_struct_loggers()
    # Reset logging
    logging.shutdown()
    reload(logging)


def check_backend(backend):
    if backend in [SimBackend.PROJECTQ, SimBackend.QUTIP]:
        assert has_module.main(backend), f"To use {backend} as backend you need to install the package"


def run_backend(node_names, backend=SimBackend.STABILIZER):
    logger.debug(f"Starting simulaqron backend process with nodes {node_names}")
    check_backend(backend=backend)
    simulaqron_settings.backend = backend
    network = Network(name="default", nodes=node_names, force=True, new=True)
    # network = Network(name="default", nodes=node_names, force=True, new=False)
    network.start(wait_until_running=False)
    # while network.running:
    # while True:
    #     sleep(0.1)
    # logger.debug("End backend process")
    return network


def run_applications(
    applications,
    instr_log_dir=None,
    # network_config=None,
    results_file=None,
    # q_formalism=ns.QFormalism.KET, TODO
    flavour=None,
    backend=SimBackend.STABILIZER
):
    """Executes functions containing application scripts,

    Parameters
    ----------
    applications : dict
        Keys should be names of nodes
        Values should be the functions
    """
    node_names = list(applications.keys())
    apps = [applications[node_name] for node_name in node_names]

    with Pool(len(node_names) + 1) as executor:
        # Start the backend process
        # backend_future = executor.apply_async(run_backend, (node_names,))
        # backend_future = executor.submit(run_backend, node_names)
        # backend_future = executor.amap(run_backend, [node_names])

        network = run_backend(node_names, backend=backend)

        # Start the application processes
        app_futures = []
        for app in apps:
            if isinstance(app, tuple):
                app_func, kwargs = app
                # future = executor.apply_async(app_func, kwds=kwargs)
                future = executor.submit(app_func, **kwargs)
                # future = executor.amap(app_func, kwargs)
            else:
                # future = executor.apply_async(app)
                future = executor.submit(app)
            app_futures.append(future)

        # Join the application processes and the backend
        # names = ['backend'] + [f'app_{node_name}' for node_name in node_names]
        names = [f'app_{node_name}' for node_name in node_names]
        results = {}
        # for future, name in as_completed([backend_future] + app_futures, names=names):
        for future, name in as_completed(app_futures, names=names):
            # results[name] = future.get()
            print(f"name {name} completed")
            results[name] = future.result()
        if results_file is not None:
            save_results(results=results, results_file=results_file)

        print("CALLING network stop")
        network.stop()
        print("CALLED network stop")

    reset(save_loggers=True)
    return results


def save_results(results, results_file):
    dump_yaml(data=results, file_path=results_file)
