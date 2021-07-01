from asyncio.futures import Future

def future_add_callback(f: Future):
    def _wrapper(callback: callable):
        f.add_done_callback(callback)
    return _wrapper


# if __name__ == '__main__':
#     import asyncio
#     loop = asyncio.get_event_loop()
#     waiter = Future()
#     @future_add_callback(waiter)
#     def test(f):
#         print(123)
#
#     waiter.set_result('123')
#     loop.run_forever()
