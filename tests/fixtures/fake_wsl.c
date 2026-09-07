#include <stdio.h>

int main(void) {
    static char input[1500000];
    static const char response[] =
        "eyJraW5kIjoicmVzcG9uc2UiLCJyZXF1ZXN0SWQiOiJyZWxheS1zZWxmLXRlc3QiLCJvayI6dHJ1ZSwiZGF0YSI6eyJuYW1lIjoiZGUucHJvamVrdF9rYW5iYW4uYWdlbnQiLCJ2ZXJzaW9uIjoiMC4xLjciLCJwcm90b2NvbCI6MX19\n";
    if (fgets(input, sizeof(input), stdin) == NULL) {
        return 1;
    }
    fputs(response, stdout);
    fflush(stdout);
    return 0;
}
