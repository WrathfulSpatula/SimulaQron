import abc
import random
from queue import Empty
from types import GeneratorType

from twisted.internet.defer import inlineCallbacks

# from pydynaa import EventType, EventExpression
# from netsquid.protocols import NodeProtocol
# from netsquid_magic.sleeper import Sleeper

from netqasm.parsing import deserialize
from netqasm.logging import get_netqasm_logger
from netqasm.messages import MessageType, Signal
# from netqasm.instructions.flavour import VanillaFlavour, NVFlavour

from simulaqron.netqasm_backend.executioner import VanillaSimulaQronExecutioner
from simulaqron.sdk.messages import MsgDoneMessage
# from squidasm.executioner.vanilla import VanillaNetSquidExecutioner
# from squidasm.executioner.nv import NVNetSquidExecutioner
# from squidasm.queues import get_queue, Signal


# TODO how to know which are wait events?
_WAIT_EVENT_NAMES = ["ANY_EVENT", "LOOP", "WAIT"]


# def is_waiting_event(event):
#     if isinstance(event, EventType):
#         tp = event
#     elif isinstance(event, EventExpression):
#         tp = event.atomic_type
#         if tp is None:
#             raise ValueError("Not an atomic event expression")
#     else:
#         raise TypeError(f"Not an Event or EventExpression, but {type(event)}")
#     return tp.name in _WAIT_EVENT_NAMES


# class Task:
#     """Keeps track of a task qnodeos has and if it's finished or waiting.
#     """
#     def __init__(self, gen, msg):
#         self._gen = gen
#         self._msg = msg
#         self._next_event = None
#         self._is_finished = False
#         self._is_waiting = False

#     @property
#     def msg(self):
#         return self._msg

#     @property
#     def is_finished(self):
#         return self._is_finished

#     @property
#     def is_waiting(self):
#         return self._is_waiting

#     def pop_next_event(self):
#         if self._next_event is None:
#             self.update_next_event()
#         if self.is_finished:
#             raise IndexError("No more events")
#         next_event = self._next_event
#         self._next_event = None
#         return next_event

#     def update_next_event(self):
#         if self._next_event is not None:
#             return
#         try:
#             next_event = next(self._gen)
#         except StopIteration:
#             self._is_finished = True
#             self._is_waiting = False
#             return

#         self._is_waiting = is_waiting_event(next_event)
#         self._next_event = next_event


class SubroutineHandler:
    def __init__(self, name, instr_log_dir=None, flavour=None, **kwargs):
        """An extremely simplified version of QNodeOS for handling NetQASM subroutines"""
        self.name = name

        self.flavour = flavour

        self._executioner = self._get_executioner_class(flavour=flavour)(name=name, instr_log_dir=instr_log_dir, **kwargs)

        # self._message_queue = get_queue(self.node.name, create_new=True)

        self._message_handlers = self._get_message_handlers()

        # Keep track of active apps
        self._active_app_ids = set()

        # Keep track of tasks to execute
        # self._subroutine_tasks = []
        # self._other_tasks = []

        # Keep track of finished messages
        self._finished_messages = []

        self._finished = False

        self._logger = get_netqasm_logger(f"{self.__class__.__name__}({self.name})")

    @classmethod
    @abc.abstractmethod
    def _get_executioner_class(cls, flavour=None):
        pass

    @abc.abstractmethod
    def stop(self):
        pass

    @property
    def finished(self):
        return self._finished

    @inlineCallbacks
    def handle_netqasm_message(self, msg_id, msg):
        yield from self._handle_message(msg_id=msg_id, msg=msg)
    
    # @inlineCallbacks
    def _handle_message(self, msg_id, msg):
        # Generator
        self._logger.info(f'Handle message {msg}')
        # yield from self._message_handlers[msg.TYPE](msg)
        output = self._message_handlers[msg.TYPE](msg)
        if isinstance(output, GeneratorType):
            yield from output
        self._mark_message_finished(msg_id=msg_id, msg=msg)
        if self.finished:
            self.stop()

    @property
    def has_active_apps(self):
        return len(self._active_app_ids) > 0

    @property
    def network_stack(self):
        return self._executioner.network_stack

    @network_stack.setter
    def network_stack(self, network_stack):
        self._executioner.network_stack = network_stack

    # def get_epr_reaction_handler(self):
    #     return self._executioner._handle_epr_response

    def _get_message_handlers(self):
        return {
            MessageType.SIGNAL: self._handle_signal,
            MessageType.SUBROUTINE: self._handle_subroutine,
            MessageType.INIT_NEW_APP: self._handle_init_new_app,
            MessageType.STOP_APP: self._handle_stop_app,
            MessageType.OPEN_EPR_SOCKET: self._handle_open_epr_socket,
        }

    def add_network_stack(self, network_stack):
        self._executioner.network_stack = network_stack

    # def _handle_message(self, msg):
    #     # Generator
    #     self._logger.info(f'Handle message {msg}')
    #     output = self._message_handlers[msg.type](msg.msg)
    #     if isinstance(output, GeneratorType):
    #         # If generator then add to this to the current task
    #         # Distinguish subroutines from others to prioritize others
    #         if msg.type == MessageType.SUBROUTINE:
    #             self._logger.debug('Adding to subroutine tasks')
    #             self._subroutine_tasks.append(Task(gen=output, msg=msg))
    #         else:
    #             self._logger.debug('Adding to other tasks')
    #             self._other_tasks.append(Task(gen=output, msg=msg))
    #     else:
    #         # No generator so directly finished
    #         self._mark_message_finished(msg=msg)

    # def _get_next_task_event(self):
    #     # Execute other tasks (non subroutine first and in order)
    #     task = self._get_next_other_task()
    #     if task is not None:
    #         self._logger.debug('Executing other task')
    #         try:
    #             return task.pop_next_event()
    #         except IndexError:
    #             return None
    #     # Only subroutine handlers left
    #     # Execute in order unless a subroutine is waiting
    #     self._logger.debug('Executing subroutine task')
    #     task = self._get_next_subroutine_task()
    #     if task is None:
    #         self._logger.debug('No more subroutine tasks')
    #         return None
    #     else:
    #         try:
    #             return task.pop_next_event()
    #         except IndexError:
    #             return None

    @abc.abstractmethod
    def _mark_message_finished(self, msg_id, msg):
        pass
        # self._logger.debug(f"Marking message {msg} as done")
        # self._finished_messages.append(msg)
        # self._task_done(item=msg)

    # def _get_next_other_task(self):
    #     if len(self._other_tasks) == 0:
    #         return None
    #     task = self._other_tasks[0]
    #     if task.is_finished:
    #         self._other_tasks.pop(0)
    #         self._mark_message_finished(msg=task.msg)
    #         return self._get_next_other_task()
    #     return task

    # def _get_next_subroutine_task(self):
    #     # Check for finished tasks
    #     to_remove = []
    #     for i, task in enumerate(self._subroutine_tasks):
    #         if task.is_finished:
    #             to_remove.append(i)
    #             self._mark_message_finished(msg=task.msg)
    #     for i in reversed(to_remove):
    #         self._subroutine_tasks.pop(i)
    #     if len(self._subroutine_tasks) == 0:
    #         return None
    #     for i, task in enumerate(self._subroutine_tasks):
    #         if not task.is_waiting:
    #             return task
    #     # All tasks are waiting so return first
    #     self._logger.info('All subroutines are waiting')
    #     return random.choice(self._subroutine_tasks)

    # def _next_message(self):
    #     try:
    #         item = self._message_queue.get(block=False)
    #     except Empty:
    #         item = None
    #     return item

    # @inlineCallbacks
    def _handle_subroutine(self, msg):
        subroutine = deserialize(msg.subroutine, flavour=self.flavour)
        self._logger.debug(f"Executing next subroutine "
                           f"from app ID {subroutine.app_id}")
        yield from self._execute_subroutine(subroutine=subroutine)

    # @inlineCallbacks
    def _execute_subroutine(self, subroutine):
        yield from self._executioner.execute_subroutine(subroutine=subroutine)

    # def _task_done(self, item):
    #     self._message_queue.task_done(item=item)

    def _handle_init_new_app(self, msg):
        app_id = msg.app_id
        self._add_app(app_id=app_id)
        max_qubits = msg.max_qubits
        self._logger.debug(f"Allocating a new "
                           f"unit module of size {max_qubits} for application with app ID {app_id}.\n")
        self._executioner.init_new_application(
            app_id=app_id,
            max_qubits=max_qubits,
        )

    def _add_app(self, app_id):
        self._active_app_ids.add(app_id)

    def _remove_app(self, app_id):
        self._active_app_ids.remove(app_id)

    def _handle_stop_app(self, msg):
        app_id = msg.app_id
        self._remove_app(app_id=app_id)
        self._logger.debug(f"Stopping application with app ID {app_id}")
        self._executioner.stop_application(app_id=app_id)

    def _handle_signal(self, msg):
        signal = Signal(msg.signal)
        self._logger.debug(f"SubroutineHandler at node {self.name} handles the signal {signal}")
        if signal == Signal.STOP:
            self._logger.debug(f"SubroutineHandler at node {self.name} will stop")
            # Just mark that it will stop, to first send back the reply
            self._finished = True
        else:
            raise ValueError(f"Unkown signal {signal}")

    # @inlineCallbacks
    def _handle_open_epr_socket(self, msg):
        yield from self._executioner.setup_epr_socket(
            epr_socket_id=msg.epr_socket_id,
            remote_node_id=msg.remote_node_id,
            remote_epr_socket_id=msg.remote_epr_socket_id,
        )


class SimulaQronSubroutineHandler(SubroutineHandler):
    def __init__(self, factory, instr_log_dir=None, flavour=None):
        super().__init__(factory.name, instr_log_dir=instr_log_dir, flavour=flavour)

        self.factory = factory

        # Give a way for the executioner to return messages
        self._executioner.add_return_msg_func(self._return_msg)

        # Give the executioner a handle to the factory
        self._executioner.add_factory(self.factory)

    @property
    def protocol(self):
        return self._protocol

    @protocol.setter
    def protocol(self, protocol):
        self._protocol = protocol

    @classmethod
    def _get_executioner_class(cls, flavour=None):
        return VanillaSimulaQronExecutioner

    def _mark_message_finished(self, msg_id, msg):
        ret_msg = MsgDoneMessage(msg_id=msg_id)
        self._return_msg(msg=ret_msg)

    def stop(self):
        print("STOPPING HANDLER")
        self.factory.stop()

    def _return_msg(self, msg):
        """Return a message to the host"""
        assert self._protocol is not None, "Seems protocol of handler has not yet been set"
        self.protocol._return_msg(msg=bytes(msg))
