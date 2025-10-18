# Section: Acknowledge safety decision
# Copied from the docs, with a minimal scaffolding around execute_function_calls
# to show where safety fields are picked up and appended later.

import termcolor

def get_safety_confirmation(safety_decision):
    """Prompt user for confirmation when safety check is triggered."""
    termcolor.cprint("Safety service requires explicit confirmation!", color="red")
    print(safety_decision["explanation"])

    decision = ""
    while decision.lower() not in ("y", "n", "ye", "yes", "no"):
        decision = input("Do you wish to proceed? [Y]es/[N]o\n")

    if decision.lower() in ("n", "no"):
        return "TERMINATE"
    return "CONTINUE"

# The following block shows where to integrate into your action loop
# This mirrors the doc snippet that adds extra_fr_fields when a safety_decision exists.

def execute_function_calls_with_safety(candidate, page, screen_width, screen_height):
    # ... Extract function calls from response ...
    function_calls = []
    for part in candidate.content.parts:
        if part.function_call:
            function_calls.append(part.function_call)

    results = []
    function_response_parts = []

    for function_call in function_calls:
        extra_fr_fields = {}

        # Check for safety decision
        if 'safety_decision' in function_call.args:
            decision = get_safety_confirmation(function_call.args['safety_decision'])
            if decision == "TERMINATE":
                print("Terminating agent loop")
                break
            extra_fr_fields["safety_acknowledgement"] = "true" # Safety acknowledgement

        # ... Execute function call and append to results ...
        # This file focuses on the safety snippet only, so execution is omitted.
        results.append((function_call.name, extra_fr_fields))

    return results

# If the user confirms, you must include the safety acknowledgement in your FunctionResponse.
# The doc snippet:
#
# function_response_parts.append(
#     FunctionResponse(
#         name=name,
#         response={"url": current_url,
#                   **extra_fr_fields},  # Include safety acknowledgement
#         parts=[
#             types.FunctionResponsePart(
#                 inline_data=types.FunctionResponseBlob(
#                     mime_type="image/png", data=screenshot
#                 )
#              )
#            ]
#          )
#        )
