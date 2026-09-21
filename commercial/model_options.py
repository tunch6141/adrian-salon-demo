"""Explicit API compatibility for the bounded preview model comparison."""


def response_options(model, output_tokens, temperature=0):
    if model == 'gpt-5.4-mini':
        return dict(reasoning={'effort': 'low'}, max_output_tokens=max(6000, output_tokens),
                    include=['reasoning.encrypted_content'], store=False)
    return dict(max_output_tokens=output_tokens, temperature=temperature, store=False)
