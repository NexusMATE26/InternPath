cmake_minimum_required(VERSION 3.20)
project(InternPathDSA VERSION 0.1.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(internpath_matching STATIC src/matching.cpp)
target_include_directories(internpath_matching PUBLIC include)
if(MSVC)
    target_compile_options(internpath_matching PRIVATE /W4)
else()
    target_compile_options(internpath_matching PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(internpath_dsa src/main.cpp)
target_link_libraries(internpath_dsa PRIVATE internpath_matching)

enable_testing()
add_executable(test_matching tests/test_matching.cpp)
target_link_libraries(test_matching PRIVATE internpath_matching)
add_test(NAME MatchingEngine COMMAND test_matching)

add_executable(test_dynamic_array tests/test_dynamic_array.cpp)
target_include_directories(test_dynamic_array PRIVATE include)
add_test(NAME DynamicArray COMMAND test_dynamic_array)

add_executable(test_singly_linked_list tests/test_singly_linked_list.cpp)
target_include_directories(test_singly_linked_list PRIVATE include)
add_test(NAME SinglyLinkedList COMMAND test_singly_linked_list)

add_executable(test_doubly_linked_list tests/test_doubly_linked_list.cpp)
target_include_directories(test_doubly_linked_list PRIVATE include)
add_test(NAME DoublyLinkedList COMMAND test_doubly_linked_list)

add_executable(test_stack tests/test_stack.cpp)
target_include_directories(test_stack PRIVATE include)
add_test(NAME Stack COMMAND test_stack)

add_executable(test_circular_queue tests/test_circular_queue.cpp)
target_include_directories(test_circular_queue PRIVATE include)
add_test(NAME CircularQueue COMMAND test_circular_queue)

add_executable(test_hash_table tests/test_hash_table.cpp)
target_include_directories(test_hash_table PRIVATE include)
add_test(NAME HashTable COMMAND test_hash_table)

add_executable(test_avl_tree tests/test_avl_tree.cpp)
target_include_directories(test_avl_tree PRIVATE include)
add_test(NAME AVLTree COMMAND test_avl_tree)

add_executable(test_catalogue tests/test_catalogue.cpp)
target_include_directories(test_catalogue PRIVATE include)
add_test(NAME InternshipCatalogue COMMAND test_catalogue)


