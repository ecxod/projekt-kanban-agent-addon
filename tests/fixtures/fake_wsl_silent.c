#include <stdio.h>

int main(void) {
    static char input[1500000];
    (void)fgets(input, sizeof(input), stdin);
    return 0;
}
