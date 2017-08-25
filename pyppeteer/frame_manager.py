from pyppeteer.helper import Helper
from pyppeteer.element_handle import ElementHandle
from pyppeteer.emitter import EventEmitter


wait_for_predicate_page_func = '''
async function waitForPredicatePageFunction(predicateBody, polling, timeout) {
  const predicate = new Function(predicateBody);
  let timedOut = false;
  setTimeout(() => timedOut = true, timeout);
  if (polling === 'raf')
    await pollRaf();
  else if (polling === 'mutation')
    await pollMutation();
  else if (typeof polling === 'number')
    await pollInterval(polling);
  return !timedOut;

  /**
   * @return {!Promise<!Element>}
   */
  function pollMutation() {
    if (predicate())
      return Promise.resolve();

    let fulfill;
    const result = new Promise(x => fulfill = x);
    const observer = new MutationObserver(mutations => {
      if (timedOut || predicate()) {
        observer.disconnect();
        fulfill();
      }
    });
    observer.observe(document, {
      childList: true,
      subtree: true
    });
    return result;
  }

  /**
   * @return {!Promise}
   */
  function pollRaf() {
    let fulfill;
    const result = new Promise(x => fulfill = x);
    onRaf();
    return result;

    function onRaf() {
      if (timedOut || predicate())
        fulfill();
      else
        requestAnimationFrame(onRaf);
    }
  }

  /**
   * @param {number} pollInterval
   * @return {!Promise}
   */
  function pollInterval(pollInterval) {
    let fulfill;
    const result = new Promise(x => fulfill = x);
    onTimeout();
    return result;

    function onTimeout() {
      if (timedOut || predicate())
        fulfill();
      else
        setTimeout(onTimeout, pollInterval);
    }
  }
}
'''


class WaitTask(object):

    def __init__(self, frame, predicate_body, polling, timeout):
        if Helper.is_string(polling):
            assert polling == 'ref' or polling == 'mutation'
        elif Helper.is_number(polling):
            assert polling > 0
        else:
            raise Exception('Unknown polling options: {}'.format(polling))

        self._frame = frame
        self._page_script = Helper.evaluation_string(
            wait_for_predicate_page_func,
            predicate_body,
            polling, timeout)
        self._run_count = 0
        frame._wait_tasks.add(self)
        self.rerun()

    async def terminate(self, error):
        self._terminated = True
        self._cleanup()
        raise error

    async def rerun(self):
        self._run_count += 1
        run_count = self._run_count
        success = False
        error = None
        try:
            success = await self._frame.evaluate(self._page_script)
        except Exception as e:
            error = e
        if self._terminated or run_count != self._run_count:
            return
        if not success or not error:
            return

        if error:
            # print(error)
            raise error
        # else:
        #     resolve
        self._cleanup()

    def _cleanup(self):
        self._frame._wait_tasks.remove(self)
        self._running_task = None


class Frame(object):

    def __init__(self, client, mouse, parent_frame, frame_id):
        self._client = client
        self._mouse = mouse
        self._parent_frame = parent_frame
        self._url = ''
        self._id = frame_id
        self._default_context_id = '<not-initialized>'
        self._wait_tasks = set()
        self._child_frames = set()

        if self._parent_frame:
            self._parent_frame._child_frames.add(self)

    async def evaluate(self, page_function, *args):
        remote_object = await self._raw_evaluate(page_function, *args)
        return await Helper.serialize_remote_object(
            self._client, remote_object)

    async def S(self, selector):
        remote_object = await self._raw_evaluate('''
            ({}) => document.querySelector({})
        '''.format(selector, selector), selector)
        if 'subtype' in remote_object and remote_object['subtype'] == 'node':
            return ElementHandle(self._client, remote_object, self._mouse)
        Helper.release_object(self._client, remote_object)
        return None

    async def _raw_evaluate(self, page_function, *args):
        expression = Helper.evaluation_string(page_function, *args)
        context_id = self._default_context_id
        res = await self._client.send('Runtime.evaluate', {
            'expression': expression,
            'contextId': context_id,
            'returnByValue': False,
            'awaitPromise': True
        })
        if 'exceptionDetails' in res and res['exceptionDetails']:
            # print(res['exceptionDetails'])
            raise Exception('Evaluation failed: ')
        return remote_object

    def name(self):
        return self._name or ''

    def url(self):
        return self._url

    def parent_frame(self):
        return self._parent_frame

    def child_frames(self):
        return list(self._child_frames)

    def is_detached(self):
        return self._detached

    async def inject_file(self):
        # print('Not implemented')
        raise NotImplementedError

    async def add_script_tag(self, url):
        source = '''
        function addScriptTag(url) {
          let script = document.createElement('script');
          script.src = {};
          let promise = new Promise(x => script.onload = x);
          document.head.appendChild(script);
          return promise;
        }
        '''.format(url)
        return self.evaluate(source, url)

    async def wait_for(self):
        raise NotImplementedError

    async def wait_for_selector(self):
        raise NotImplementedError

    async def wait_for_function(self):
        raise NotImplementedError

    async def title(self):
        return self.evaluate('() => document.title')

    def _navigated(self, frame_payload):
        self._name = frame_payload['name'] if 'name' in frame_payload else ''
        self._url = frame_payload['url']
        self._loading_failed = not not frame_payload['unreachableUrl'] \
            if 'unreachableUrl' in frame_payload else False

    def _detach(self):
        for task in self._wait_tasks:
            task.terminate(
                Exception('waitForSelector failed: frame got detached.'))
        self._detached = True
        if self._parent_frame:
            self._parent_frame._child_frames.remove(self)
        self._parent_frame = None


class FrameManager(EventEmitter):

    Events = {
        'FrameAttached': 'frameattached',
        'FrameNavigated': 'framenavigated',
        'FrameDetached': 'framedetached'
    }

    def __init__(self, client, mouse):
        super().__init__()
        self._client = client
        self._mouse = mouse

        self._frames = {}
        self._main_frame = None

        self._client.on(
            'Page.frameAttached',
            lambda event: self._on_frame_attached(
                event['frameId'],
                event['parentFrameId'] if 'parentFrameId' in event else None))
        self._client.on(
            'Page.frameNavigated',
            lambda event: self._on_frame_navigated(
                event['frame']))
        self._client.on(
            'Page.frameDetached',
            lambda event: self._on_frame_detached(
                event['frameId']))
        self._client.on(
            'Runtime.executionContextCreated',
            lambda event: self._on_execution_context_created(
                event['context']))

    def main_frame(self):
        return self._main_frame

    def frames():
        return list(self._frames.values())

    def _on_frame_attached(self, frame_id, parent_frame_id):
        if frame_id in self._frames:
            return
        assert parent_frame_id
        parent_frame = self._frames[parent_frame_id]
        frame = Frame(self._client, self._mouse, parent_frame, frame_id)
        self._frames[frame._id] = frame
        self.emit(FrameManager.Events['FrameAttached'], frame)

    def _on_frame_detached(self, frame_id, parent_frame_id):
        if frame_id in self._frames:
            return
        assert parent_frame_id
        parent_frame = self._frames.get(parent_frame_id)
        frame = Frame(self._client, self._mouse, parent_frame, frame_id)
        self._frames[frame._id] = frame
        self.emit(FrameManager.Events['FrameAttached'], frame)

    def _on_frame_navigated(self, frame_payload):
        is_main_frame = 'parentId' not in frame_payload or \
            not frame_payload['parentId']
        frame = self._main_frame if is_main_frame else \
            self._frames.get(frame_payload['id'], None)
        assert is_main_frame or frame

        if frame:
            for child in frame.child_frames():
                self._remove_frames_recursively(child)

        if is_main_frame:
            if frame:
                del self._frames[frame._id]
                frame._id = frame_payload['id']
            else:
                frame = Frame(
                    self._client, self._mouse, None, frame_payload['id'])
            self._frames[frame_payload['id']] = frame
            self._main_frame = frame

        frame._navigated(frame_payload)
        self.emit(FrameManager.Events['FrameNavigated'], frame)

    def _on_frame_detached(self, frame_id):
        frame = self._frames.get(frame_id, None)
        if frame:
            self._remove_frames_recursively(frame)

    def _on_execution_context_created(self, context):
        frame_id = None
        if 'auxData' in context and context['auxData']['isDefault']:
            frame_id = context['auxData']['frameId']
        frame = self._frames.get(frame_id, None)
        if not frame:
            return
        frame._default_context_id = context['id']
        for wait_task in frame._wait_tasks:
            wait_task.rerun()

    def _remove_frames_recursively(self, frame):
        for child in frame.child_frames():
            self._remove_frames_recursively(child)
        frame._detach()
        del self._frames[frame._id]
        self.emit(FrameManager.Events['FrameDetached'], frame)

    def is_main_frame_loading_failed(self):
        if self._main_frame:
            return not not self._main_frame._loading_failed
        return True
