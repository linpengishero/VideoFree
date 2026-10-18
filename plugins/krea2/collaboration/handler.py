async def director(request, runtime):
    return await runtime.single(request)
