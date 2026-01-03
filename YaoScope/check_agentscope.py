import agentscope
import inspect
import pkgutil

print('AgentScope version:', agentscope.__version__)
print('\nAvailable modules:')
for importer, modname, ispkg in pkgutil.iter_modules(agentscope.__path__, prefix='agentscope.'):
    print(' -', modname)

print('\n\nChecking models:')
try:
    import agentscope.models
    print('agentscope.models exists')
    print('Contents:', dir(agentscope.models))
except ImportError as e:
    print(f'agentscope.models NOT FOUND: {e}')

try:
    import agentscope.model
    print('\nagentscope.model exists')
    print('Contents:', dir(agentscope.model))
except ImportError as e:
    print(f'\nagentscope.model NOT FOUND: {e}')

print('\n\nLooking for ChatModel classes:')
try:
    from agentscope.models import DashScopeChatWrapper
    print('Found: DashScopeChatWrapper')
except ImportError:
    print('DashScopeChatWrapper NOT FOUND')

try:
    from agentscope.models import OpenAIChatWrapper
    print('Found: OpenAIChatWrapper')
except ImportError:
    print('OpenAIChatWrapper NOT FOUND')

