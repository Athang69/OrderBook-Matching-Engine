cmake_minimum_required(VERSION 3.16)
project(orderbook_engine CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
add_compile_options(-Wall -Wextra -Wpedantic)

add_library(ob STATIC src/order_book.cpp)
target_include_directories(ob PUBLIC include)

# The matching engine process the backend talks to.
add_executable(ob_engine src/main.cpp)
target_link_libraries(ob_engine PRIVATE ob)

add_executable(ob_tests tests/test_order_book.cpp)
target_link_libraries(ob_tests PRIVATE ob)

add_executable(ob_bench bench/bench.cpp)
target_link_libraries(ob_bench PRIVATE ob)

enable_testing()
add_test(NAME order_book COMMAND ob_tests)
