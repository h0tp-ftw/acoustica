def check_braces(filename):
    with open(filename, "r") as f:
        lines = f.readlines()

    stack = []

    for i, line in enumerate(lines):
        line_num = i + 1
        for char in line:
            if char == "{":
                stack.append(line_num)
            elif char == "}":
                if not stack:
                    print(f"Error: Unexpected '}}' at line {line_num}")
                    return
                stack.pop()

    if stack:
        print(f"Error: Unclosed '{{' at line {stack[-1]}")
    else:
        print("All braces are balanced.")


check_braces("/var/home/uwu/Documents/vscode/engine/src/acoustic_engine/tuner/styles.css")
