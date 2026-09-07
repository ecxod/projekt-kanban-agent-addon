#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif

#include <windows.h>
#include <fcntl.h>
#include <io.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#define MAX_MESSAGE (1024U * 1024U)
#define MAX_CONFIG_BYTES 65535U
#define READ_BUFFER_SIZE 8192U

static const char BASE64_ALPHABET[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

typedef struct {
    HANDLE handle;
    unsigned char buffer[READ_BUFFER_SIZE];
    DWORD offset;
    DWORD length;
} buffered_reader;

typedef struct {
    HANDLE child_stdout;
    HANDLE browser_stdout;
} output_relay_args;

typedef struct {
    HANDLE process;
    HANDLE stdin_write;
    HANDLE stdout_read;
} child_process;

static volatile LONG shutting_down = 0;
static wchar_t log_path[MAX_PATH];

static void log_error(const wchar_t *message) {
    HANDLE log = CreateFileW(
        log_path,
        FILE_APPEND_DATA,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        NULL,
        OPEN_ALWAYS,
        FILE_ATTRIBUTE_NORMAL,
        NULL
    );
    if (log == INVALID_HANDLE_VALUE) {
        return;
    }
    if (GetFileSize(log, NULL) == 0) {
        const wchar_t bom = 0xfeff;
        DWORD bom_written = 0;
        WriteFile(log, &bom, sizeof(bom), &bom_written, NULL);
    }
    SYSTEMTIME now;
    wchar_t line[1024];
    GetLocalTime(&now);
    int count = _snwprintf(
        line,
        sizeof(line) / sizeof(line[0]),
        L"%04u-%02u-%02u %02u:%02u:%02u %ls\r\n",
        now.wYear,
        now.wMonth,
        now.wDay,
        now.wHour,
        now.wMinute,
        now.wSecond,
        message
    );
    if (count > 0) {
        DWORD written = 0;
        WriteFile(log, line, (DWORD)count * sizeof(wchar_t), &written, NULL);
    }
    CloseHandle(log);
}

static int self_test_error(int code, const wchar_t *message) {
    log_error(message);
    fwprintf(stderr, L"%ls\n", message);
    fflush(stderr);
    return code;
}

static int write_all(HANDLE handle, const unsigned char *data, DWORD length) {
    DWORD offset = 0;
    while (offset < length) {
        DWORD written = 0;
        if (!WriteFile(handle, data + offset, length - offset, &written, NULL) || written == 0) {
            return 0;
        }
        offset += written;
    }
    return 1;
}

static int read_exact(HANDLE handle, unsigned char *data, DWORD length, int allow_eof) {
    DWORD offset = 0;
    while (offset < length) {
        DWORD received = 0;
        if (!ReadFile(handle, data + offset, length - offset, &received, NULL) || received == 0) {
            return allow_eof && offset == 0 ? 0 : -1;
        }
        offset += received;
    }
    return 1;
}

static char *base64_encode(const unsigned char *input, DWORD length, DWORD *output_length) {
    DWORD encoded_length = ((length + 2U) / 3U) * 4U;
    char *output = (char *)malloc((size_t)encoded_length + 2U);
    if (!output) {
        return NULL;
    }
    DWORD source = 0;
    DWORD target = 0;
    while (source < length) {
        uint32_t value = (uint32_t)input[source++] << 16;
        int bytes = 1;
        if (source < length) {
            value |= (uint32_t)input[source++] << 8;
            bytes++;
        }
        if (source < length) {
            value |= input[source++];
            bytes++;
        }
        output[target++] = BASE64_ALPHABET[(value >> 18) & 63U];
        output[target++] = BASE64_ALPHABET[(value >> 12) & 63U];
        output[target++] = bytes >= 2 ? BASE64_ALPHABET[(value >> 6) & 63U] : '=';
        output[target++] = bytes == 3 ? BASE64_ALPHABET[value & 63U] : '=';
    }
    output[target++] = '\n';
    output[target] = '\0';
    *output_length = target;
    return output;
}

static int base64_value(unsigned char character) {
    if (character >= 'A' && character <= 'Z') return character - 'A';
    if (character >= 'a' && character <= 'z') return character - 'a' + 26;
    if (character >= '0' && character <= '9') return character - '0' + 52;
    if (character == '+') return 62;
    if (character == '/') return 63;
    return -1;
}

static unsigned char *base64_decode(const char *input, DWORD length, DWORD *output_length) {
    if (length == 0 || length % 4U != 0) {
        return NULL;
    }
    DWORD padding = 0;
    if (length && input[length - 1] == '=') padding++;
    if (length > 1 && input[length - 2] == '=') padding++;
    DWORD decoded_length = (length / 4U) * 3U - padding;
    if (decoded_length < 2U || decoded_length > MAX_MESSAGE) {
        return NULL;
    }
    unsigned char *output = (unsigned char *)malloc(decoded_length);
    if (!output) {
        return NULL;
    }
    DWORD source = 0;
    DWORD target = 0;
    while (source < length) {
        int a = base64_value((unsigned char)input[source++]);
        int b = base64_value((unsigned char)input[source++]);
        int c = input[source] == '=' ? 0 : base64_value((unsigned char)input[source]);
        source++;
        int d = input[source] == '=' ? 0 : base64_value((unsigned char)input[source]);
        source++;
        if (a < 0 || b < 0 || c < 0 || d < 0) {
            free(output);
            return NULL;
        }
        uint32_t value = ((uint32_t)a << 18) | ((uint32_t)b << 12) |
                         ((uint32_t)c << 6) | (uint32_t)d;
        if (target < decoded_length) output[target++] = (unsigned char)(value >> 16);
        if (target < decoded_length) output[target++] = (unsigned char)(value >> 8);
        if (target < decoded_length) output[target++] = (unsigned char)value;
    }
    *output_length = decoded_length;
    return output;
}

static int reader_byte(buffered_reader *reader, unsigned char *value) {
    if (reader->offset >= reader->length) {
        reader->offset = 0;
        reader->length = 0;
        if (!ReadFile(reader->handle, reader->buffer, READ_BUFFER_SIZE, &reader->length, NULL) ||
            reader->length == 0) {
            return 0;
        }
    }
    *value = reader->buffer[reader->offset++];
    return 1;
}

static char *read_base64_line(buffered_reader *reader, DWORD *line_length) {
    DWORD capacity = 4096;
    DWORD length = 0;
    DWORD maximum = ((MAX_MESSAGE + 2U) / 3U) * 4U + 2U;
    char *line = (char *)malloc(capacity);
    if (!line) {
        return NULL;
    }
    unsigned char character;
    while (reader_byte(reader, &character)) {
        if (character == '\n') {
            if (length && line[length - 1] == '\r') length--;
            line[length] = '\0';
            *line_length = length;
            return line;
        }
        if (length + 1U >= maximum) {
            free(line);
            return NULL;
        }
        if (length + 1U >= capacity) {
            DWORD next_capacity = capacity * 2U;
            if (next_capacity > maximum) next_capacity = maximum;
            char *resized = (char *)realloc(line, next_capacity);
            if (!resized) {
                free(line);
                return NULL;
            }
            line = resized;
            capacity = next_capacity;
        }
        line[length++] = (char)character;
    }
    free(line);
    return NULL;
}

static char *read_config_file(const wchar_t *path, DWORD *length) {
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (file == INVALID_HANDLE_VALUE) return NULL;
    DWORD size = GetFileSize(file, NULL);
    if (size == INVALID_FILE_SIZE || size == 0 || size > MAX_CONFIG_BYTES) {
        CloseHandle(file);
        return NULL;
    }
    char *data = (char *)malloc((size_t)size + 1U);
    if (!data) {
        CloseHandle(file);
        return NULL;
    }
    DWORD received = 0;
    if (!ReadFile(file, data, size, &received, NULL) || received != size) {
        free(data);
        CloseHandle(file);
        return NULL;
    }
    CloseHandle(file);
    data[size] = '\0';
    *length = size;
    return data;
}

static wchar_t *utf8_to_wide(const char *text) {
    int required = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text, -1, NULL, 0);
    if (required <= 0) return NULL;
    wchar_t *wide = (wchar_t *)malloc((size_t)required * sizeof(wchar_t));
    if (!wide) return NULL;
    if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text, -1, wide, required)) {
        free(wide);
        return NULL;
    }
    return wide;
}

static int load_config(wchar_t **wsl_path, wchar_t **distribution, wchar_t **host_path) {
    wchar_t executable[MAX_PATH];
    if (!GetModuleFileNameW(NULL, executable, MAX_PATH)) return 0;
    wchar_t *separator = wcsrchr(executable, L'\\');
    if (!separator) return 0;
    *separator = L'\0';
    _snwprintf(log_path, MAX_PATH, L"%ls\\relay.log", executable);
    wchar_t config_path[MAX_PATH];
    _snwprintf(config_path, MAX_PATH, L"%ls\\relay-config.txt", executable);

    DWORD data_length = 0;
    char *data = read_config_file(config_path, &data_length);
    if (!data) return 0;
    char *lines[3] = {NULL, NULL, NULL};
    DWORD line_count = 0;
    char *cursor = data;
    lines[line_count++] = cursor;
    for (DWORD index = 0; index < data_length; index++) {
        if (data[index] == '\r') data[index] = '\0';
        if (data[index] == '\n') {
            data[index] = '\0';
            if (line_count < 3) lines[line_count++] = data + index + 1;
        }
    }
    if (line_count != 3 || !lines[0][0] || !lines[2][0]) {
        free(data);
        return 0;
    }
    *wsl_path = utf8_to_wide(lines[0]);
    *distribution = utf8_to_wide(lines[1]);
    *host_path = utf8_to_wide(lines[2]);
    free(data);
    if (!*wsl_path || !*distribution || !*host_path ||
        wcschr(*wsl_path, L'"') || wcschr(*distribution, L'"') || wcschr(*host_path, L'"')) {
        free(*wsl_path);
        free(*distribution);
        free(*host_path);
        return 0;
    }
    return 1;
}

static int start_wsl_child(
    const wchar_t *wsl_path,
    const wchar_t *distribution,
    const wchar_t *host_path,
    child_process *child
) {
    SECURITY_ATTRIBUTES attributes = {sizeof(SECURITY_ATTRIBUTES), NULL, TRUE};
    HANDLE stdin_read = NULL;
    HANDLE stdout_write = NULL;
    HANDLE stderr_log = CreateFileW(
        log_path,
        FILE_APPEND_DATA,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        &attributes,
        OPEN_ALWAYS,
        FILE_ATTRIBUTE_NORMAL,
        NULL
    );
    if (!CreatePipe(&stdin_read, &child->stdin_write, &attributes, 0) ||
        !CreatePipe(&child->stdout_read, &stdout_write, &attributes, 0)) {
        if (stdin_read) CloseHandle(stdin_read);
        if (child->stdin_write) CloseHandle(child->stdin_write);
        if (child->stdout_read) CloseHandle(child->stdout_read);
        if (stdout_write) CloseHandle(stdout_write);
        if (stderr_log != INVALID_HANDLE_VALUE) CloseHandle(stderr_log);
        return 0;
    }
    SetHandleInformation(child->stdin_write, HANDLE_FLAG_INHERIT, 0);
    SetHandleInformation(child->stdout_read, HANDLE_FLAG_INHERIT, 0);

    size_t command_size = wcslen(wsl_path) + wcslen(distribution) + wcslen(host_path) + 160U;
    wchar_t *command = (wchar_t *)malloc(command_size * sizeof(wchar_t));
    if (!command) return 0;
    if (distribution[0]) {
        _snwprintf(
            command,
            command_size,
            L"\"%ls\" --distribution \"%ls\" --exec python3 \"%ls\" --base64-native-bridge",
            wsl_path,
            distribution,
            host_path
        );
    } else {
        _snwprintf(
            command,
            command_size,
            L"\"%ls\" --exec python3 \"%ls\" --base64-native-bridge",
            wsl_path,
            host_path
        );
    }

    STARTUPINFOW startup;
    PROCESS_INFORMATION process;
    ZeroMemory(&startup, sizeof(startup));
    ZeroMemory(&process, sizeof(process));
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = stdin_read;
    startup.hStdOutput = stdout_write;
    startup.hStdError = stderr_log != INVALID_HANDLE_VALUE ? stderr_log : GetStdHandle(STD_ERROR_HANDLE);
    BOOL started = CreateProcessW(
        wsl_path,
        command,
        NULL,
        NULL,
        TRUE,
        CREATE_NO_WINDOW,
        NULL,
        NULL,
        &startup,
        &process
    );
    free(command);
    CloseHandle(stdin_read);
    CloseHandle(stdout_write);
    if (stderr_log != INVALID_HANDLE_VALUE) CloseHandle(stderr_log);
    if (!started) {
        CloseHandle(child->stdin_write);
        CloseHandle(child->stdout_read);
        return 0;
    }
    CloseHandle(process.hThread);
    child->process = process.hProcess;
    return 1;
}

static DWORD WINAPI relay_child_output(LPVOID parameter) {
    output_relay_args *args = (output_relay_args *)parameter;
    buffered_reader reader = {args->child_stdout, {0}, 0, 0};
    while (1) {
        DWORD line_length = 0;
        char *line = read_base64_line(&reader, &line_length);
        if (!line) break;
        DWORD message_length = 0;
        unsigned char *message = base64_decode(line, line_length, &message_length);
        free(line);
        if (!message) {
            log_error(L"Invalid base64 response from WSL native host.");
            break;
        }
        unsigned char header[4] = {
            (unsigned char)(message_length & 0xffU),
            (unsigned char)((message_length >> 8) & 0xffU),
            (unsigned char)((message_length >> 16) & 0xffU),
            (unsigned char)((message_length >> 24) & 0xffU)
        };
        int success = write_all(args->browser_stdout, header, 4) &&
                      write_all(args->browser_stdout, message, message_length);
        free(message);
        if (!success) break;
        FlushFileBuffers(args->browser_stdout);
    }
    if (InterlockedCompareExchange(&shutting_down, 0, 0) == 0) {
        log_error(L"WSL native host disconnected unexpectedly.");
        ExitProcess(12);
    }
    return 0;
}

static int relay_browser_input(HANDLE browser_input, HANDLE child_input) {
    while (1) {
        unsigned char header[4];
        int status = read_exact(browser_input, header, 4, 1);
        if (status == 0) return 1;
        if (status < 0) return 0;
        DWORD length = (DWORD)header[0] | ((DWORD)header[1] << 8) |
                       ((DWORD)header[2] << 16) | ((DWORD)header[3] << 24);
        if (length < 2U || length > MAX_MESSAGE) {
            log_error(L"Firefox sent an invalid native message length.");
            return 0;
        }
        unsigned char *message = (unsigned char *)malloc(length);
        if (!message) return 0;
        if (read_exact(browser_input, message, length, 0) < 1) {
            free(message);
            return 0;
        }
        DWORD encoded_length = 0;
        char *encoded = base64_encode(message, length, &encoded_length);
        free(message);
        if (!encoded) return 0;
        int success = write_all(child_input, (unsigned char *)encoded, encoded_length);
        free(encoded);
        if (!success) return 0;
        FlushFileBuffers(child_input);
    }
}

static int self_test(child_process *child) {
    static const unsigned char request[] =
        "{\"kind\":\"request\",\"requestId\":\"relay-self-test\",\"action\":\"hello\",\"payload\":{}}";
    DWORD encoded_length = 0;
    char *encoded = base64_encode(request, (DWORD)strlen((const char *)request), &encoded_length);
    if (!encoded) return self_test_error(21, L"Relay self-test could not encode its request.");
    int sent = write_all(child->stdin_write, (unsigned char *)encoded, encoded_length);
    free(encoded);
    if (!sent) return self_test_error(22, L"Relay self-test could not write its request to WSL.");
    CloseHandle(child->stdin_write);
    child->stdin_write = NULL;

    buffered_reader reader = {child->stdout_read, {0}, 0, 0};
    DWORD line_length = 0;
    char *line = read_base64_line(&reader, &line_length);
    if (!line) return self_test_error(23, L"Relay self-test received no response line from the WSL native host.");
    DWORD response_length = 0;
    unsigned char *response = base64_decode(line, line_length, &response_length);
    free(line);
    if (!response) return self_test_error(24, L"Relay self-test received an invalid base64 response from WSL.");
    char *text = (char *)malloc((size_t)response_length + 1U);
    if (!text) {
        free(response);
        return self_test_error(25, L"Relay self-test could not allocate its response buffer.");
    }
    memcpy(text, response, response_length);
    text[response_length] = '\0';
    free(response);
    int success = strstr(text, "\"requestId\":\"relay-self-test\"") != NULL &&
                  strstr(text, "\"ok\":true") != NULL &&
                  strstr(text, "\"name\":\"de.projekt_kanban.agent\"") != NULL &&
                  strstr(text, "\"protocol\":1") != NULL;
    if (!success) {
        self_test_error(26, L"The WSL native host returned an unexpected relay self-test response.");
    }
    free(text);
    return success ? 0 : 26;
}

int wmain(int argc, wchar_t **argv) {
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
    wchar_t *wsl_path = NULL;
    wchar_t *distribution = NULL;
    wchar_t *host_path = NULL;
    if (!load_config(&wsl_path, &distribution, &host_path)) {
        log_error(L"Cannot read relay-config.txt.");
        return 2;
    }
    child_process child = {NULL, NULL, NULL};
    if (!start_wsl_child(wsl_path, distribution, host_path, &child)) {
        log_error(L"Cannot start wsl.exe.");
        free(wsl_path);
        free(distribution);
        free(host_path);
        return 3;
    }
    free(wsl_path);
    free(distribution);
    free(host_path);

    if (argc == 2 && wcscmp(argv[1], L"--self-test") == 0) {
        int result = self_test(&child);
        WaitForSingleObject(child.process, 5000);
        CloseHandle(child.stdout_read);
        CloseHandle(child.process);
        return result;
    }

    output_relay_args args = {child.stdout_read, GetStdHandle(STD_OUTPUT_HANDLE)};
    HANDLE output_thread = CreateThread(NULL, 0, relay_child_output, &args, 0, NULL);
    if (!output_thread) {
        log_error(L"Cannot create output relay thread.");
        TerminateProcess(child.process, 4);
        return 4;
    }
    int success = relay_browser_input(GetStdHandle(STD_INPUT_HANDLE), child.stdin_write);
    InterlockedExchange(&shutting_down, 1);
    CloseHandle(child.stdin_write);
    WaitForSingleObject(child.process, 5000);
    WaitForSingleObject(output_thread, 5000);
    CloseHandle(output_thread);
    CloseHandle(child.stdout_read);
    CloseHandle(child.process);
    return success ? 0 : 5;
}
