"""
Scheduler queues
"""

import marshal
from six.moves import cPickle as pickle

from queuelib import queue

def _serializable_queue(queue_class, serialize, deserialize):

    class SerializableQueue(queue_class):

        def push(self, obj):
            s = serialize(obj)
            super(SerializableQueue, self).push(s)

        def pop(self):
            s = super(SerializableQueue, self).pop()
            if s:
                return deserialize(s)

    return SerializableQueue

def _pickle_serialize(obj):
    try:
        return pickle.dumps(obj, protocol=2)
    # Python <= 3.4 raises pickle.PicklingError here while
    # 3.5 <= Python < 3.6 raises AttributeError and
    # Python >= 3.6 raises TypeError
    except (pickle.PicklingError, AttributeError, TypeError) as e:
        raise ValueError(str(e))

## 先进先出磁盘队列（pickle 序列化）
PickleFifoDiskQueue = _serializable_queue(queue.FifoDiskQueue, \
    _pickle_serialize, pickle.loads)
## 后进先出磁盘队列（pickle 序列化）
PickleLifoDiskQueue = _serializable_queue(queue.LifoDiskQueue, \
    _pickle_serialize, pickle.loads)
## 先进先出磁盘队列（marshal 序列化）
MarshalFifoDiskQueue = _serializable_queue(queue.FifoDiskQueue, \
    marshal.dumps, marshal.loads)
## 后进先出磁盘队列（marshal 序列化）
MarshalLifoDiskQueue = _serializable_queue(queue.LifoDiskQueue, \
    marshal.dumps, marshal.loads)
## 先进先出内存队列
FifoMemoryQueue = queue.FifoMemoryQueue
## 后进先出内存队列
LifoMemoryQueue = queue.LifoMemoryQueue
